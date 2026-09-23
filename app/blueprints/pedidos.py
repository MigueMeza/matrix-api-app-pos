from flask import Blueprint, g, jsonify, request

from ..auth import turno_required
from ..db import db_cursor
from .clientes import ClienteInvalido, resolver_cliente
from .ventas import VentaInvalida, registrar_venta

pedidos_bp = Blueprint("pedidos", __name__)


def _lineas_sin_asignar(cursor, pedido_id):
    """Líneas fuera de catálogo que todavía no tienen un producto real asignado."""
    cursor.execute(
        """
        SELECT descripcion, talla FROM pedido_detalles
        WHERE pedido_id = %s AND producto_id IS NULL
        """,
        (pedido_id,),
    )
    return [f"{d['descripcion']} ({d['talla']})" if d["talla"] else d["descripcion"] for d in cursor.fetchall()]


@pedidos_bp.route("/pedidos", methods=["GET"])
@turno_required
def listar():
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.fecha_pedido, p.fecha_disponible, p.estado, p.observaciones,
                   p.venta_id, p.apartado_id, p.tienda_id,
                   c.nombre AS cliente_nombre, c.telefono AS cliente_telefono,
                   t.nombre AS tienda_nombre
            FROM pedidos p
            JOIN clientes c ON c.id = p.cliente_id
            JOIN tiendas t ON t.id = p.tienda_id
            ORDER BY p.fecha_pedido DESC
            """
        )
        pedidos = cursor.fetchall()

        detalles_por_pedido = {}
        if pedidos:
            ids = [p["id"] for p in pedidos]
            # LEFT JOIN: las líneas fuera de catálogo no tienen producto (ni precio) todavía
            cursor.execute(
                f"""
                SELECT pd.id AS detalle_id, pd.pedido_id, pd.producto_id, pd.cantidad, pd.comentario,
                       COALESCE(pr.nombre, pd.descripcion) AS nombre,
                       COALESCE(pr.talla, pd.talla) AS talla,
                       pr.color, pr.precio, pr.codigo_barras
                FROM pedido_detalles pd
                LEFT JOIN productos pr ON pr.id = pd.producto_id
                WHERE pd.pedido_id IN ({", ".join(["%s"] * len(ids))})
                ORDER BY pd.id
                """,
                ids,
            )
            for d in cursor.fetchall():
                detalles_por_pedido.setdefault(d.pop("pedido_id"), []).append(
                    {**d, "precio": float(d["precio"]) if d["precio"] is not None else None}
                )

    for pedido in pedidos:
        items = detalles_por_pedido.get(pedido["id"], [])
        pedido["items"] = items
        # El total solo suma lo que ya tiene precio; precio_pendiente avisa que falta definir el resto
        pedido["total"] = sum(i["precio"] * i["cantidad"] for i in items if i["precio"] is not None)
        pedido["precio_pendiente"] = any(i["precio"] is None for i in items)
        # Solo se puede convertir en venta/apartado desde una terminal de la misma tienda
        pedido["de_esta_tienda"] = pedido["tienda_id"] == g.turno["tienda_id"]

    return jsonify(pedidos=pedidos), 200


@pedidos_bp.route("/pedidos", methods=["POST"])
@turno_required
def nuevo():
    datos = request.get_json(silent=True) or {}
    cliente_id = datos.get("cliente_id")
    cliente_nombre = (datos.get("cliente_nombre") or "").strip()
    cliente_telefono = (datos.get("cliente_telefono") or "").strip() or None
    observaciones = (datos.get("observaciones") or "").strip() or None
    # Cada item es del catálogo    { "producto_id": 1, "cantidad": 2, "comentario": "..." }
    # o fuera de catálogo           { "descripcion": "Chamarra de gala", "talla": "M", "cantidad": 1, "comentario": "roja o negra" }
    items_raw = datos.get("items", [])

    items = []  # (producto_id | None, descripcion | None, talla | None, cantidad, comentario | None)
    try:
        cliente_id = int(cliente_id) if cliente_id else None
        for item in items_raw:
            cantidad = int(item.get("cantidad") or 0)
            if cantidad <= 0:
                return jsonify(error="Cada producto del pedido necesita una cantidad mayor a 0."), 400

            comentario = (item.get("comentario") or "").strip()[:255] or None
            producto_id = item.get("producto_id")
            descripcion = (item.get("descripcion") or "").strip()[:150]

            if producto_id:
                items.append((int(producto_id), None, None, cantidad, comentario))
            elif descripcion:
                talla = (item.get("talla") or "").strip()[:20] or None
                items.append((None, descripcion, talla, cantidad, comentario))
            else:
                return jsonify(error="Cada producto necesita elegirse del catálogo o llevar una descripción."), 400
    except (TypeError, ValueError, AttributeError):
        return jsonify(error="Los datos del pedido no son válidos."), 400

    if not cliente_id and not cliente_nombre:
        return jsonify(error="Selecciona un cliente existente o captura uno nuevo."), 400
    if not items:
        return jsonify(error="Agrega al menos un producto al pedido."), 400

    with db_cursor(commit=True) as cursor:
        # Validar antes de insertar: un id inexistente haría fallar la FK con un 500
        producto_ids = sorted({i[0] for i in items if i[0] is not None})
        if producto_ids:
            cursor.execute(
                f"SELECT COUNT(*) AS n FROM productos WHERE activo = 1 AND id IN ({', '.join(['%s'] * len(producto_ids))})",
                producto_ids,
            )
            if cursor.fetchone()["n"] != len(producto_ids):
                return jsonify(error="Uno de los productos no existe o está descontinuado."), 400

        try:
            cliente_id = resolver_cliente(cursor, cliente_id, cliente_nombre, cliente_telefono)
        except ClienteInvalido as e:
            return jsonify(error=e.mensaje), 400

        cursor.execute(
            """
            INSERT INTO pedidos (tienda_id, cliente_id, usuario_id, observaciones)
            VALUES (%s, %s, %s, %s)
            """,
            (g.turno["tienda_id"], cliente_id, g.turno["usuario_id"], observaciones),
        )
        pedido_id = cursor.lastrowid

        for producto_id, descripcion, talla, cantidad, comentario in items:
            cursor.execute(
                """
                INSERT INTO pedido_detalles (pedido_id, producto_id, descripcion, talla, cantidad, comentario)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (pedido_id, producto_id, descripcion, talla, cantidad, comentario),
            )

    return jsonify(mensaje="Pedido creado exitosamente.", pedido_id=pedido_id), 201


@pedidos_bp.route("/pedidos/<int:pedido_id>/convertir_venta", methods=["POST"])
@turno_required
def convertir_venta(pedido_id):
    """Cobra un pedido disponible como venta, con los pagos que capturó el cajero (efectivo, tarjeta, mixto...)."""
    datos = request.get_json(silent=True) or {}

    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                "SELECT * FROM pedidos WHERE id = %s AND estado = 'disponible' FOR UPDATE",
                (pedido_id,),
            )
            pedido = cursor.fetchone()
            if not pedido:
                raise VentaInvalida("Este pedido ya no está disponible para convertirse.")
            if pedido["tienda_id"] != g.turno["tienda_id"]:
                raise VentaInvalida("Este pedido pertenece a otra tienda.", 403)
            if _lineas_sin_asignar(cursor, pedido_id):
                raise VentaInvalida("Hay productos del pedido sin precio: el administrador debe asignarlos al catálogo.")

            cursor.execute(
                "SELECT producto_id, cantidad FROM pedido_detalles WHERE pedido_id = %s",
                (pedido_id,),
            )
            items = [(d["producto_id"], d["cantidad"]) for d in cursor.fetchall()]

            # La mercancía del pedido no está en el inventario (quedó reservada al llegar): no se descuenta
            venta = registrar_venta(cursor, g.turno, items, datos.get("pagos", []), descontar_inventario=False)

            cursor.execute(
                "UPDATE pedidos SET estado = 'entregado', venta_id = %s WHERE id = %s AND estado = 'disponible'",
                (venta["venta_id"], pedido_id),
            )
    except VentaInvalida as e:
        return jsonify(error=e.mensaje), e.status

    return jsonify(mensaje=f"Pedido convertido en venta #{venta['venta_id']}.", **venta), 200


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
        if _lineas_sin_asignar(cursor, pedido_id):
            return jsonify(error="Hay productos del pedido sin precio: el administrador debe asignarlos al catálogo."), 400

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