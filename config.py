import os

# Sin valor por defecto: la base vive solo en la VM, y un arranque local no debe crear una propia.
SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
TARIFA = int(os.environ.get("TARIFA", "1500"))
