import os
import hmac
from datetime import datetime
from flask import Flask, jsonify, redirect, render_template, request, url_for, flash
from models import db, Vehiculo, Paso

app = Flask(__name__)
app.config.from_pyfile("config.py")
app.secret_key = "dev"
db.init_app(app)

with app.app_context():
    db.create_all()


# Deja solo letras y números en mayúscula, así "ab-12 cd" y "AB12CD" cuentan como la misma patente.
def norm(patente):
    return "".join(c for c in (patente or "").upper() if c.isalnum())


# Marca como pagados todos los pasos pendientes de la patente y devuelve el monto total cobrado.
def pagar_pendientes(patente):
    pendientes = Paso.query.filter_by(patente=patente, pagado=False).all()
    for p in pendientes:
        p.pagado = True
        p.pagado_en = datetime.now()
    db.session.commit()
    return sum(p.precio for p in pendientes)


@app.get("/")
def dashboard():
    q = norm(request.args.get("patente"))
    pasos = Paso.query.order_by(Paso.fecha.desc())
    if q:
        pasos = pasos.filter(Paso.patente.like(f"%{q}%"))
    pasos = pasos.limit(100).all()
    total = db.session.query(db.func.coalesce(db.func.sum(Paso.precio), 0)).scalar()
    pendiente = db.session.query(db.func.coalesce(db.func.sum(Paso.precio), 0)).filter_by(pagado=False).scalar()
    return render_template(
        "dashboard.html",
        pasos=pasos,
        q=q,
        total=total,
        pendiente=pendiente,
        n_pasos=Paso.query.count(),
        n_veh=Vehiculo.query.count(),
    )


@app.route("/vehiculos", methods=["GET", "POST"])
def vehiculos():
    if request.method == "POST":
        patente = norm(request.form.get("patente"))
        if not patente:
            flash("Ingresa una patente válida", "danger")
        elif Vehiculo.query.filter_by(patente=patente).first():
            flash("Esa patente ya está registrada", "warning")
        else:
            v = Vehiculo(patente=patente, propietario=request.form.get("propietario", "").strip())
            db.session.add(v)
            db.session.commit()
            Paso.query.filter_by(patente=patente).update({"vehiculo_id": v.id})
            db.session.commit()
            flash(f"Vehículo {patente} registrado", "success")
        return redirect(url_for("vehiculos"))
    return render_template("vehiculos.html", vehiculos=Vehiculo.query.order_by(Vehiculo.creado.desc()).all())


@app.get("/pagar")
def pagar_inicio():
    q = norm(request.args.get("patente"))
    if q:
        return redirect(url_for("pagar", patente=q))
    return render_template("pagar_inicio.html")


@app.route("/pagar/<patente>", methods=["GET", "POST"])
def pagar(patente):
    patente = norm(patente)
    pendientes = Paso.query.filter_by(patente=patente, pagado=False).order_by(Paso.fecha).all()
    if not pendientes:
        flash(f"{patente} no tiene cobros pendientes", "info")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        monto = pagar_pendientes(patente)
        flash(f"Pago de ${monto:,} confirmado para {patente}".replace(",", "."), "success")
        return redirect(url_for("dashboard"))
    return render_template("checkout.html", patente=patente, pendientes=pendientes, total=sum(p.precio for p in pendientes))


def crear_paso(patente, precio=None):
    v = Vehiculo.query.filter_by(patente=patente).first()
    paso = Paso(patente=patente, vehiculo_id=v.id if v else None, precio=precio or app.config["TARIFA"])
    db.session.add(paso)
    db.session.commit()
    return paso


@app.post("/api/pasos")
def api_paso():
    data = request.get_json(silent=True) or {}
    patente = norm(data.get("patente"))
    if not patente:
        return jsonify(error="patente requerida"), 400
    return jsonify(crear_paso(patente, int(data.get("precio") or 0)).to_dict()), 201


# Endpoints para el hardware: responden texto plano para que la placa no tenga que leer JSON.
# Piden la clave HW_KEY en ?k=. Si la variable no está definida (desarrollo local) no se exige.
@app.before_request
def exigir_clave_hw():
    clave = os.environ.get("HW_KEY")
    if clave and request.path.startswith("/hw/"):
        if not hmac.compare_digest(request.args.get("k", ""), clave):
            return "", 401


@app.get("/hw/paso")
def hw_paso():
    patente = norm(request.args.get("patente"))
    if not patente:
        return "", 400
    return str(crear_paso(patente).id)


@app.get("/hw/pagado/<int:paso_id>")
def hw_pagado(paso_id):
    return "1" if db.get_or_404(Paso, paso_id).pagado else "0"


@app.get("/api/pasos/<int:paso_id>")
def api_paso_estado(paso_id):
    return jsonify(db.get_or_404(Paso, paso_id).to_dict())


@app.get("/api/pasos")
def api_pasos():
    return jsonify([p.to_dict() for p in Paso.query.order_by(Paso.fecha.desc()).limit(200)])


@app.post("/api/vehiculos")
def api_vehiculo():
    data = request.get_json(silent=True) or {}
    patente = norm(data.get("patente"))
    if not patente:
        return jsonify(error="patente requerida"), 400
    v = Vehiculo.query.filter_by(patente=patente).first()
    if v:
        return jsonify(v.to_dict()), 200
    v = Vehiculo(patente=patente, propietario=(data.get("propietario") or "").strip())
    db.session.add(v)
    db.session.commit()
    # El hardware puede registrar pasos antes de que el dueño se registre: se enlazan por patente.
    Paso.query.filter_by(patente=patente).update({"vehiculo_id": v.id})
    db.session.commit()
    return jsonify(v.to_dict()), 201


@app.get("/api/vehiculos/<patente>")
def api_vehiculo_estado(patente):
    v = Vehiculo.query.filter_by(patente=norm(patente)).first_or_404()
    return jsonify(v.to_dict())


@app.post("/api/pagos")
def api_pago():
    data = request.get_json(silent=True) or {}
    patente = norm(data.get("patente"))
    if not Paso.query.filter_by(patente=patente).first():
        return jsonify(error="sin registros para esa patente"), 404
    return jsonify(patente=patente, pagado=pagar_pendientes(patente))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
