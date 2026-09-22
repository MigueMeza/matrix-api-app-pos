from flask import Blueprint, g, jsonify, request

from ..auth import turno_required
from ..db import db_cursor

pedidos_bp = Blueprint("pedidos", __name__)


@pedidos_bp.route("/pedidos", methods=["GET"])
@turno_required
def listar():
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.fecha_pedido, p.fecha_disponible, p.estado, p.observaciones,
                   c.nombre AS cliente_nombre, c.telefono AS cliente_telefono,
                   t.nombre AS tienda_nombre
            FROM pedidos p
            JOIN clientes c ON c.id = p.cliente_id
            JOIN tiendas t ON t.id = p.tienda_id
            ORDER BY p.fecha_pedido DESC
            """
        )
        pedidos = cursor.fetchall()

    return jsonify(pedidos=pedidos), 200


@pedidos_bp.route("/pedidos", methods=["POST"])
@turno_required
def nuevo():
    datos = request.get_json(silent=True) or {}
    cliente_id = datos.get("cliente_id")
    cliente_nombre = (datos.get("cliente_nombre") or "").strip()
    cliente_telefono = (datos.get("cliente_telefono") or "").strip() or None
    observaciones = (datos.get("observaciones") or "").strip() or None
    items_raw = datos.get("items", [])  # Espera [{ "producto_id": 1, "cantidad": 2 }]

    items = []
    for item in items_raw:
        pid = item.get("producto_id")
        cant = item.get("cantidad")
        if pid and cant and int(cant) > 0:
            items.append((int(pid), int(cant)))

    if not cliente_id and not cliente_nombre:
        return jsonify(error="Selecciona un cliente existente o captura uno nuevo."), 400
    if not items:
        return jsonify(error="Agrega al menos un producto al pedido."), 400

    with db_cursor(commit=True) as cursor:
        if not cliente_id:
            cursor.execute(
                "INSERT INTO clientes (nombre, telefono) VALUES (%s, %s)",
                (cliente_nombre, cliente_telefono),
            )
            cliente_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO pedidos (tienda_id, cliente_id, usuario_id, observaciones)
            VALUES (%s, %s, %s, %s)
            """,
            (g.turno["tienda_id"], cliente_id, g.turno["usuario_id"], observaciones),
        )
        pedido_id = cursor.lastrowid

        for producto_id, cantidad in items:
            cursor.execute(
                "INSERT INTO pedido_detalles (pedido_id, producto_id, cantidad) VALUES (%s, %s, %s)",
                (pedido_id, producto_id, cantidad),
            )

    return jsonify(mensaje="Pedido creado exitosamente.", pedido_id=pedido_id), 201


@pedidos_bp.route("/pedidos/<int:pedido_id>/convertir_venta", methods=["POST"])
@turno_required
def convertir_venta(pedido_id):
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT * FROM pedidos WHERE id = %s AND estado = 'disponible' FOR UPDATE",
            (pedido_id,),
        )
        pedido = cursor.fetchone()
        if not pedido:
            return jsonify(error="Este pedido ya no está disponible para convertirse."), 400
        if pedido["tienda_id"] != g.turno["tienda_id"]:
            return jsonify(error="Este pedido pertenece a otra tienda."), 403

        cursor.execute(
            """
            SELECT pd.producto_id, pd.cantidad, p.precio,
                   i.id AS inventario_id, COALESCE(i.cantidad, 0) AS stock
            FROM pedido_detalles pd
            JOIN productos p ON p.id = pd.producto_id
            LEFT JOIN inventarios i ON i.producto_id = pd.producto_id AND i.tienda_id = %s
            WHERE pd.pedido_id = %s
            """,
            (g.turno["tienda_id"], pedido_id),
        )
        detalles = cursor.fetchall()

        for detalle in detalles:
            if not detalle["inventario_id"] or detalle["stock"] < detalle["cantidad"]:
                return jsonify(error="No hay inventario suficiente en esta tienda para completar la venta."), 409

        total = sum(float(detalle["precio"]) * detalle["cantidad"] for detalle in detalles)

        cursor.execute(
            "INSERT INTO ventas (tienda_id, usuario_id, turno_id, total) VALUES (%s, %s, %s, %s)",
            (g.turno["tienda_id"], g.turno["usuario_id"], g.turno["id"], total),
        )
        venta_id = cursor.lastrowid

        for detalle in detalles:
            cursor.execute(
                """
                INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s)
                """,
                (venta_id, detalle["producto_id"], detalle["cantidad"], detalle["precio"]),
            )
            cursor.execute(
                "UPDATE inventarios SET cantidad = cantidad - %s WHERE id = %s",
                (detalle["cantidad"], detalle["inventario_id"]),
            )

        cursor.execute("SELECT id FROM metodos_pago WHERE nombre = 'efectivo'")
        metodo_efectivo_id = cursor.fetchone()["id"]
        cursor.execute(
            "INSERT INTO venta_pagos (venta_id, metodo_pago_id, monto) VALUES (%s, %s, %s)",
            (venta_id, metodo_efectivo_id, total),
        )

        cursor.execute(
            "UPDATE pedidos SET estado = 'entregado', venta_id = %s WHERE id = %s AND estado = 'disponible'",
            (venta_id, pedido_id),
        )

    return jsonify(mensaje=f"Pedido convertido en venta #{venta_id}.", venta_id=venta_id), 200


@pedidos_bp.route("/pedidos/<int:pedido_id>/convertir_apartado", methods=["POST"])
@turno_required
def convertir_apartado(pedido_id):
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT * FROM pedidos WHERE id = %s AND estado = 'disponible' FOR UPDATE",
            (pedido_id,),
        )
        pedido = cursor.fetchone()
        if not pedido:
            return jsonify(error="Este pedido ya no está disponible para convertirse."), 400
        if pedido["tienda_id"] != g.turno["tienda_id"]:
            return jsonify(error="Este pedido pertenece a otra tienda."), 403

        cursor.execute(
            """
            SELECT pd.producto_id, pd.cantidad, p.precio
            FROM pedido_detalles pd
            JOIN productos p ON p.id = pd.producto_id
            WHERE pd.pedido_id = %s
            """,
            (pedido_id,),
        )
        detalles = cursor.fetchall()
        total = sum(float(detalle["precio"]) * detalle["cantidad"] for detalle in detalles)

        cursor.execute(
            """
            INSERT INTO apartados (tienda_id, cliente_id, usuario_id, fecha_limite, total)
            VALUES (%s, %s, %s, DATE_ADD(CURDATE(), INTERVAL 3 MONTH), %s)
            """,
            (pedido["tienda_id"], pedido["cliente_id"], g.turno["usuario_id"], total),
        )
        apartado_id = cursor.lastrowid

        for detalle in detalles:
            cursor.execute(
                """
                INSERT INTO apartado_detalles (apartado_id, producto_id, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s)
                """,
                (apartado_id, detalle["producto_id"], detalle["cantidad"], detalle["precio"]),
            )

        cursor.execute(
            "UPDATE pedidos SET estado = 'entregado', apartado_id = %s WHERE id = %s AND estado = 'disponible'",
            (apartado_id, pedido_id),
        )

    return jsonify(mensaje=f"Pedido convertido en apartado #{apartado_id}.", apartado_id=apartado_id), 200