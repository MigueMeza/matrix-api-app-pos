from datetime import date, datetime, timezone

from flask import Flask, jsonify
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

from .config import Config


class JSONProvider(DefaultJSONProvider):
    """Fechas en ISO 8601 en lugar del formato HTTP que usa Flask por defecto.

    MySQL corre en UTC y los DATETIME llegan sin zona, así que se marcan como UTC
    ("2026-09-22T21:06:45+00:00"); cada cliente los convierte a su hora local.
    """

    @staticmethod
    def default(o):
        if isinstance(o, datetime):
            return (o if o.tzinfo else o.replace(tzinfo=timezone.utc)).isoformat()
        if isinstance(o, date):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.json = JSONProvider(app)
    app.config.from_object(config_class)

    # 1. Habilitar CORS para permitir peticiones desde otras aplicaciones/dominios
    CORS(app)

    # Importar blueprints
    from .blueprints.admin import admin_bp
    from .blueprints.apartados import apartados_bp
    from .blueprints.auth import auth_bp
    from .blueprints.caja import caja_bp
    from .blueprints.clientes import clientes_bp
    from .blueprints.core import core_bp
    from .blueprints.pedidos import pedidos_bp
    from .blueprints.productos import productos_bp
    from .blueprints.ventas import ventas_bp

    # Registrar blueprints
    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(caja_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(productos_bp)
    app.register_blueprint(apartados_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(admin_bp)

    # 2. Manejadores de error en formato JSON (para evitar que Flask devuelva HTML si algo falla)
    @app.errorhandler(404)
    def no_encontrado(e):
        return jsonify(error="Recurso o endpoint no encontrado."), 404

    @app.errorhandler(500)
    def error_servidor(e):
        return jsonify(error="Error interno del servidor."), 500

    return app