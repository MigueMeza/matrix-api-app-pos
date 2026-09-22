import os


def _variable_requerida(nombre):
    valor = os.environ.get(nombre)
    if not valor:
        raise RuntimeError(
            f"La variable de entorno {nombre} es obligatoria. Sin ella, la app no debe arrancar: "
            f"sin un valor único la sesión no está protegida (ver .env)."
        )
    return valor


class Config:
    VERSION = "2.0.2"

    # Sin valor por defecto a propósito: si esto tuviera un fallback, cualquiera
    # que leyera este archivo podría forjar una cookie de sesión con rol =
    # super_admin y entrar a /admin sin contraseña.
    SECRET_KEY = _variable_requerida("SECRET_KEY")

    DB_HOST = os.environ.get("DB_HOST", "db")
    DB_USER = os.environ.get("DB_USER", "admin")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "admin123")
    DB_NAME = os.environ.get("DB_NAME", "matrix")
