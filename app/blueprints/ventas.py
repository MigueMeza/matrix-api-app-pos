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


class VentaInvalida(Exception):
    """Error de negocio al registrar una venta: se responde con este mensaje y status."""

    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


def registrar_venta(cursor, turno, items, pagos, descontar_inventario=True):
    """Registra una venta completa dentro de la transacción del cursor.

    items: [(producto_id, cantidad)]. pagos: [{"metodo_pago_id", "monto"}] tal como llegan del cliente.
    Revalida precios y stock contra la base, descuenta inventario y guarda los pagos.
    Con descontar_inventario=False (entrega de un pedido) no revisa ni descuenta existencias:
    esa mercancía nunca entró al inventario, estaba reservada para el cliente.
    Lanza VentaInvalida si algo no cuadra; como no se hace commit, nada queda a medias.
    Lo usan /ventas/finalizar y /pedidos/<id>/convertir_venta.
    """
    if not items:
        raise VentaInvalida("El ticket está vacío.")
    if not pagos:
        raise VentaInvalida("No se ha registrado ningún pago.")

    tienda_id = turno["tienda_id"]

    metodos_validos = {m["id"] for m in _metodos_pago(cursor)}
    pagos_normalizados = []
    total_pagado = 0.0
    try:
        for pago in pagos:
            metodo_pago_id = int(pago["metodo_pago_id"])
            monto = float(pago["monto"])
            if metodo_pago_id not in metodos_validos or monto <= 0:
                raise VentaInvalida("Hay un pago inválido en la lista.")
            pagos_normalizados.append((metodo_pago_id, monto))
            total_pagado += monto
    except (KeyError, TypeError, ValueError):
        raise VentaInvalida("Hay un pago inválido en la lista.")

    total = 0.0
    detalles = []
    for producto_id, cantidad in items:
        if cantidad <= 0:
            raise VentaInvalida("Cantidad inválida en el ticket.")

        # Un pedido se entrega aunque el producto se haya descontinuado después de pedirlo
        cursor.execute(
            f"""
            SELECT p.precio, i.id AS inventario_id, COALESCE(i.cantidad, 0) AS stock
            FROM productos p
            LEFT JOIN inventarios i ON i.producto_id = p.id AND i.tienda_id = %s
            WHERE p.id = %s {"AND p.activo = 1" if descontar_inventario else ""}
            """,
            (tienda_id, producto_id),
        )
        fila = cursor.fetchone()

        if not fila:
            raise VentaInvalida("Uno de los productos del ticket ya no existe.")
        if descontar_inventario and fila["stock"] < cantidad:
            raise VentaInvalida("Ya no hay inventario suficiente para uno de los productos del ticket.", 409)

        precio_unitario = float(fila["precio"])
        total += precio_unitario * cantidad
        detalles.append((producto_id, cantidad, precio_unitario, fila["inventario_id"]))

    if total_pagado < total:
        raise VentaInvalida("El pago no cubre el total de la venta.")

    cursor.execute(
        "INSERT INTO ventas (tienda_id, usuario_id, turno_id, total) VALUES (%s, %s, %s, %s)",
        (tienda_id, turno["usuario_id"], turno["id"], total),
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
        if descontar_inventario:
            cursor.execute(
                "UPDATE inventarios SET cantidad = cantidad - %s WHERE id = %s",
                (cantidad, inventario_id),
            )

    for metodo_pago_id, monto in pagos_normalizados:
        cursor.execute(
            "INSERT INTO venta_pagos (venta_id, metodo_pago_id, monto) VALUES (%s, %s, %s)",
            (venta_id, metodo_pago_id, monto),
        )

    return {"venta_id": venta_id, "total": total, "cambio": total_pagado - total}


@ventas_bp.route("/ventas/finalizar", methods=["POST"])
@turno_required
def finalizar():
    datos = request.get_json(silent=True) or {}

    try:
        items = [(int(i["producto_id"]), int(i["cantidad"])) for i in datos.get("items", [])]
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Hay un producto inválido en el ticket."), 400

    try:
        with db_cursor(commit=True) as cursor:
            venta = registrar_venta(cursor, g.turno, items, datos.get("pagos", []))
    except VentaInvalida as e:
        return jsonify(error=e.mensaje), e.status

    return jsonify(**venta), 201
