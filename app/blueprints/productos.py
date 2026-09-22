from flask import Blueprint, jsonify, request

from ..auth import turno_required
from ..db import db_cursor

productos_bp = Blueprint("productos", __name__)


def _tiendas_activas(cursor):
    cursor.execute("SELECT id, nombre FROM tiendas WHERE activo = 1 ORDER BY nombre")
    return cursor.fetchall()


@productos_bp.route("/productos", methods=["GET"])
@turno_required
def listar():
    tienda_id = request.args.get("tienda_id", type=int, default=0)
    buscar = request.args.get("buscar", "").strip()

    with db_cursor() as cursor:
        tiendas = _tiendas_activas(cursor)

        sql = """
            SELECT p.id AS producto_id, i.id AS inventario_id, p.codigo_barras, p.nombre, p.talla, p.color,
                   p.precio, i.cantidad, t.id AS tienda_id, t.nombre AS tienda
            FROM inventarios i
            JOIN productos p ON p.id = i.producto_id
            JOIN tiendas t ON t.id = i.tienda_id
            WHERE p.activo = 1 AND t.activo = 1
        """
        parametros = []
        if tienda_id != 0:
            sql += " AND i.tienda_id = %s"
            parametros.append(tienda_id)

        # Por nombre o por código de barras (se puede escanear la etiqueta en el buscador)
        if buscar:
            sql += " AND (p.nombre LIKE %s OR p.codigo_barras = %s)"
            parametros.extend([f"%{buscar}%", buscar])

        sql += " ORDER BY p.nombre, p.talla, p.color, t.nombre"

        cursor.execute(sql, parametros)
        inventario = cursor.fetchall()

    # Formatear el precio a float para serialización JSON limpia
    for item in inventario:
        item["precio"] = float(item["precio"])

    return jsonify(tiendas=tiendas, tienda_id_seleccionada=tienda_id, inventario=inventario), 200