from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash

from ..db import db_cursor
from ..permisos import Rol

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    datos = request.get_json(silent=True) or {}
    usuario_login = (datos.get("usuario_login") or "").strip()
    password = datos.get("password") or ""

    if not usuario_login or not password:
        return jsonify(error="Debes proporcionar usuario y contraseña."), 400

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nombre, rol, password_hash
            FROM usuarios
            WHERE usuario_login = %s AND rol IN (%s, %s) AND activo = 1
            """,
            (usuario_login, Rol.SUPER_ADMIN.value, Rol.SUPERVISOR.value),
        )
        usuario = cursor.fetchone()

    if not usuario or not usuario["password_hash"] or not check_password_hash(usuario["password_hash"], password):
        return jsonify(error="Usuario o contraseña incorrectos."), 401

    session.clear()
    session["usuario_id"] = usuario["id"]
    session["nombre"] = usuario["nombre"]
    session["rol"] = usuario["rol"]
    session["contexto"] = "pos"

    return jsonify(
        mensaje="Login exitoso.",
        usuario={
            "id": usuario["id"],
            "nombre": usuario["nombre"],
            "rol": usuario["rol"],
        },
    ), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(mensaje="Sesión cerrada correctamente."), 200