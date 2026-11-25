from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Vehiculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patente = db.Column(db.String(10), unique=True, nullable=False, index=True)
    propietario = db.Column(db.String(80), default="")
    creado = db.Column(db.DateTime, default=datetime.now)
    pasos = db.relationship("Paso", backref="vehiculo", lazy=True)

    def deuda(self):
        return sum(p.precio for p in self.pasos if not p.pagado)

    def to_dict(self):
        return {"patente": self.patente, "propietario": self.propietario, "deuda": self.deuda()}


class Paso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patente = db.Column(db.String(10), nullable=False, index=True)
    vehiculo_id = db.Column(db.Integer, db.ForeignKey("vehiculo.id"), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.now, index=True)
    precio = db.Column(db.Integer, nullable=False)
    pagado = db.Column(db.Boolean, default=False)
    pagado_en = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "patente": self.patente,
            "fecha": self.fecha.isoformat(timespec="seconds"),
            "precio": self.precio,
            "pagado": self.pagado,
        }
