from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Habilitar CORS para permitir peticiones desde otras aplicaciones/dominios
    CORS(app)

    # Importar blueprints
    from .blueprints.admin import admin_bp
    from .blueprints.apartados import apartados_bp
    from .blueprints.auth import auth_bp
    from .blueprints.caja import caja_bp
    from .blueprints.core import core_bp
    from .blueprints.pedidos import pedidos_bp
    from .blueprints.productos import productos_bp
    from .blueprints.ventas import ventas_bp

    # Registrar blueprints
    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(caja_bp)
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