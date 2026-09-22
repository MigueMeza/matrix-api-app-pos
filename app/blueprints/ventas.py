from flask import Blueprint, g, jsonify, request

from ..auth import turno_required
from ..db import db_cursor

ventas_bp = Blueprint("ventas", __name__)


def _metodos_pago(cursor):
    cursor.execute("SELECT id, nombre FROM metodos_pago ORDER BY id")
    return cursor.fetchall()


@ventas_bp.route("/ventas", methods=["GET"])
@turno_required
def index():
    with db_cursor() as cursor:
        metodos_pago = _metodos_pago(cursor)
    return jsonify(turno=g.turno, metodos_pago=metodos_pago), 200


@ventas_bp.route("/ventas/buscar", methods=["GET"])
@turno_required
def buscar_producto():
    codigo_barras = request.args.get("codigo_barras", "").strip()
    tienda_id = g.turno["tienda_id"]

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.nombre, p.talla, p.color, p.precio,
                   COALESCE(i.cantidad, 0) AS stock
            FROM productos p
            LEFT JOIN inventarios i ON i.producto_id = p.id AND i.tienda_id = %s
            WHERE p.codigo_barras = %s AND p.activo = 1
            """,
            (tienda_id, codigo_barras),
        )
        producto = cursor.fetchone()

    if not producto:
        return jsonify(encontrado=False, error="Producto no encontrado."), 404

    return jsonify(
        encontrado=True,
        producto_id=producto["id"],
        codigo_barras=codigo_barras,
        nombre=producto["nombre"],
        talla=producto["talla"],
        color=producto["color"],
        precio=float(producto["precio"]),
        stock=producto["stock"],
    ), 200


@ventas_bp.route("/ventas/buscar_nombre", methods=["GET"])
@turno_required
def buscar_por_nombre():
    nombre = request.args.get("nombre", "").strip()
    tienda_id = g.turno["tienda_id"]

    if len(nombre) < 2:
        return jsonify(resultados=[]), 200

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.nombre, p.talla, p.color, p.precio, p.codigo_barras,
                   COALESCE(i.cantidad, 0) AS stock
            FROM productos p
            LEFT JOIN inventarios i ON i.producto_id = p.id AND i.tienda_id = %s
            WHERE p.activo = 1 AND p.nombre LIKE %s
            ORDER BY p.nombre, p.talla, p.color
            LIMIT 20
            """,
            (tienda_id, f"%{nombre}%"),
        )
        productos = cursor.fetchall()

    return jsonify(
        resultados=[
            {
                "producto_id": p["id"],
                "nombre": p["nombre"],
                "talla": p["talla"],
                "color": p["color"],
                "precio": float(p["precio"]),
                "codigo_barras": p["codigo_barras"],
                "stock": p["stock"],
            }
            for p in productos
        ]
    ), 200


@ventas_bp.route("/ventas/finalizar", methods=["POST"])
@turno_required
def finalizar():
    datos = request.get_json(silent=True) or {}
    items = datos.get("items", [])
    pagos = datos.get("pagos", [])

    if not items:
        return jsonify(error="El ticket está vacío."), 400

    if not pagos:
        return jsonify(error="No se ha registrado ningún pago."), 400

    tienda_id = g.turno["tienda_id"]
    usuario_id = g.turno["usuario_id"]
    turno_id = g.turno["id"]

    with db_cursor(commit=True) as cursor:
        metodos_validos = {m["id"] for m in _metodos_pago(cursor)}
        pagos_normalizados = []
        total_pagado = 0.0
        for pago in pagos:
            metodo_pago_id = int(pago["metodo_pago_id"])
            monto = float(pago["monto"])
            if metodo_pago_id not in metodos_validos or monto <= 0:
                return jsonify(error="Hay un pago inválido en la lista."), 400
            pagos_normalizados.append((metodo_pago_id, monto))
            total_pagado += monto

        total = 0.0
        detalles = []
        for item in items:
            producto_id = int(item["producto_id"])
            cantidad = int(item["cantidad"])
            if cantidad <= 0:
                return jsonify(error="Cantidad inválida en el ticket."), 400

            cursor.execute(
                """
                SELECT p.precio, i.id AS inventario_id, COALESCE(i.cantidad, 0) AS stock
                FROM productos p
                LEFT JOIN inventarios i ON i.producto_id = p.id AND i.tienda_id = %s
                WHERE p.id = %s AND p.activo = 1
                """,
                (tienda_id, producto_id),
            )
            fila = cursor.fetchone()

            if not fila or fila["stock"] < cantidad:
                return jsonify(error="Ya no hay inventario suficiente para uno de los productos del ticket."), 409

            precio_unitario = float(fila["precio"])
            total += precio_unitario * cantidad
            detalles.append((producto_id, cantidad, precio_unitario, fila["inventario_id"]))

        if total_pagado < total:
            return jsonify(error="El pago no cubre el total de la venta."), 400

        cursor.execute(
            "INSERT INTO ventas (tienda_id, usuario_id, turno_id, total) VALUES (%s, %s, %s, %s)",
            (tienda_id, usuario_id, turno_id, total),
        )
        venta_id = cursor.lastrowid

        for producto_id, cantidad, precio_unitario, inventario_id in detalles:
            cursor.execute(
                """
                INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s)
                """,
                (venta_id, producto_id, cantidad, precio_unitario),
            )
            cursor.execute(
                "UPDATE inventarios SET cantidad = cantidad - %s WHERE id = %s",
                (cantidad, inventario_id),
            )

        for metodo_pago_id, monto in pagos_normalizados:
            cursor.execute(
                "INSERT INTO venta_pagos (venta_id, metodo_pago_id, monto) VALUES (%s, %s, %s)",
                (venta_id, metodo_pago_id, monto),
            )

    return jsonify(venta_id=venta_id, total=total, cambio=total_pagado - total), 201