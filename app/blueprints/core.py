from flask import Blueprint, current_app, jsonify, session

from ..db import db_cursor

core_bp = Blueprint("core", __name__)


@core_bp.route("/", methods=["GET"])
def inicio():
    return jsonify(
        mensaje="API en funcionamiento",
        sesion={
            "turno_id": session.get("turno_id"),
            "usuario_id": session.get("usuario_id"),
            "contexto": session.get("contexto"),
        },
    ), 200


@core_bp.route("/health", methods=["GET"])
def healthcheck():
    try:
        with db_cursor() as cursor:
            cursor.execute("SELECT 1")
        return jsonify(status="ok"), 200
    except Exception as e:
        current_app.logger.error(f"Error de conexión: {e}")
        return jsonify(status="error", detalle=str(e)), 500