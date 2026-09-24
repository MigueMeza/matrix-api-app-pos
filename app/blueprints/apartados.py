from flask import Blueprint, g, jsonify, request

from ..auth import turno_required
from ..db import db_cursor
from .clientes import ClienteInvalido, resolver_cliente
from .ventas import _metodos_pago

apartados_bp = Blueprint("apartados", __name__)

# Un apartado vence a los 3 meses de creado. No se guarda en `estado`: se calcula al consultar.
VIGENCIA_MESES = 3

# Cómo ve el POS un apartado: vigente | expirado | entregado | cancelado
SQL_SITUACION = f"""
    CASE
        WHEN a.estado = 'entregado' THEN 'entregado'
        WHEN a.estado IN ('cancelado', 'vencido') THEN 'cancelado'
        WHEN NOW() > DATE_ADD(a.fecha_creacion, INTERVAL {VIGENCIA_MESES} MONTH) THEN 'expirado'
        ELSE 'vigente'
    END
"""
SQL_FECHA_VENCE = f"DATE(DATE_ADD(a.fecha_creacion, INTERVAL {VIGENCIA_MESES} MONTH))"


class ApartadoInvalido(Exception):
    """Error de negocio: se responde con este mensaje y status, y la transacción no se confirma."""

    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


def _validar_pago(cursor, pago, campo_monto="monto"):
    """(metodo_pago_id, monto, nombre_metodo) de un pago {metodo_pago_id, monto} que manda el cliente."""
    try:
        metodo_pago_id = int(pago["metodo_pago_id"])
        monto = round(float(pago[campo_monto]), 2)
    except (KeyError, TypeError, ValueError):
        raise ApartadoInvalido("Captura un monto y un método de pago válidos.")

    metodos = {m["id"]: m["nombre"] for m in _metodos_pago(cursor)}
    if metodo_pago_id not in metodos or monto <= 0:
        raise ApartadoInvalido("Captura un monto y un método de pago válidos.")
    return metodo_pago_id, monto, metodos[metodo_pago_id]


def _registrar_pago(cursor, apartado_id, metodo_pago_id, monto):
    """El abono queda ligado al turno: el corte de caja suma los abonos en efectivo."""
    cursor.execute(
        """
        INSERT INTO apartado_pagos (apartado_id, turno_id, usuario_id, monto, metodo_pago_id)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (apartado_id, g.turno["id"], g.turno["usuario_id"], monto, metodo_pago_id),
    )


def _apartado_para_cobro(cursor, apartado_id):
    """Carga el apartado bloqueado para la transacción, con su saldo, y rechaza los que ya no admiten cobros."""
    cursor.execute(
        f"""
        SELECT a.id, a.tienda_id, a.total, a.estado, {SQL_SITUACION} AS situacion,
               DATE_FORMAT({SQL_FECHA_VENCE}, '%%d/%%m/%%Y') AS vence
        FROM apartados a
        WHERE a.id = %s
        FOR UPDATE
        """,
        (apartado_id,),
    )
    apartado = cursor.fetchone()
    if not apartado:
        raise ApartadoInvalido("El apartado no existe.", 404)

    if apartado["situacion"] == "entregado":
        raise ApartadoInvalido("Este apartado ya fue entregado.")
    if apartado["situacion"] == "cancelado":
        raise ApartadoInvalido("Este apartado fue cancelado.")
    if apartado["situacion"] == "expirado":
        raise ApartadoInvalido(
            f"Este apartado expiró el {apartado['vence']}. Un administrador debe revisarlo."
        )

    cursor.execute(
        "SELECT COALESCE(SUM(monto), 0) AS abonado FROM apartado_pagos WHERE apartado_id = %s",
        (apartado_id,),
    )
    apartado["saldo"] = round(float(apartado["total"]) - float(cursor.fetchone()["abonado"]), 2)
    return apartado


@apartados_bp.route("/apartados", methods=["GET"])
@turno_required
def listar():
    with db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT a.id, a.tienda_id, t.nombre AS tienda_nombre,
                   c.nombre AS cliente_nombre, c.telefono AS cliente_telefono,
                   a.fecha_creacion, a.fecha_entrega, {SQL_FECHA_VENCE} AS fecha_vence,
                   a.estado, {SQL_SITUACION} AS situacion, a.total, a.observaciones,
                   COALESCE((SELECT SUM(p.monto) FROM apartado_pagos p WHERE p.apartado_id = a.id), 0) AS abonado
            FROM apartados a
            JOIN clientes c ON c.id = a.cliente_id
            JOIN tiendas t ON t.id = a.tienda_id
            ORDER BY a.fecha_creacion DESC
            """
        )
        apartados = cursor.fetchall()

        items_por_apartado, pagos_por_apartado = {}, {}
        if apartados:
            ids = [a["id"] for a in apartados]
            marcadores = ", ".join(["%s"] * len(ids))

            cursor.execute(
                f"""
                SELECT d.apartado_id, d.producto_id, d.cantidad, d.precio_unitario,
                       pr.nombre, pr.talla, pr.color, pr.codigo_barras
                FROM apartado_detalles d
                JOIN productos pr ON pr.id = d.producto_id
                WHERE d.apartado_id IN ({marcadores})
                ORDER BY d.id
                """,
                ids,
            )
            for d in cursor.fetchall():
                items_por_apartado.setdefault(d.pop("apartado_id"), []).append(
                    {**d, "precio_unitario": float(d["precio_unitario"])}
                )

            cursor.execute(
                f"""
                SELECT p.apartado_id, p.fecha_pago, p.monto, m.nombre AS metodo
                FROM apartado_pagos p
                JOIN metodos_pago m ON m.id = p.metodo_pago_id
                WHERE p.apartado_id IN ({marcadores})
                ORDER BY p.fecha_pago, p.id
                """,
                ids,
            )
            for p in cursor.fetchall():
                pagos_por_apartado.setdefault(p.pop("apartado_id"), []).append({**p, "monto": float(p["monto"])})

        metodos_pago = _metodos_pago(cursor)

    for a in apartados:
        a["total"] = float(a["total"])
        a["abonado"] = float(a["abonado"])
        a["saldo"] = round(a["total"] - a["abonado"], 2)
        a["items"] = items_por_apartado.get(a["id"], [])
        a["pagos"] = pagos_por_apartado.get(a["id"], [])
        # La mercancía está físicamente en su tienda: solo ahí se entrega (abonar se puede en cualquiera)
        a["de_esta_tienda"] = a["tienda_id"] == g.turno["tienda_id"]

    return jsonify(apartados=apartados, metodos_pago=metodos_pago), 200


@apartados_bp.route("/apartados", methods=["POST"])
@turno_required
def crear():
    """Aparta productos de la tienda del turno para un cliente, con un anticipo opcional.

    Las piezas salen del inventario al apartar: quedan retenidas para el cliente.
    """
    datos = request.get_json(silent=True) or {}
    observaciones = (datos.get("observaciones") or "").strip() or None

    cantidades = {}
    try:
        for item in datos.get("items", []):
            producto_id, cantidad = int(item["producto_id"]), int(item["cantidad"])
            if cantidad <= 0:
                return jsonify(error="Cada producto necesita una cantidad mayor a 0."), 400
            cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Hay un producto inválido en el apartado."), 400
    if not cantidades:
        return jsonify(error="Agrega al menos un producto al apartado."), 400

    tienda_id = g.turno["tienda_id"]
    try:
        with db_cursor(commit=True) as cursor:
            try:
                cliente_id = resolver_cliente(
                    cursor, datos.get("cliente_id"), datos.get("cliente_nombre"), datos.get("cliente_telefono")
                )
            except ClienteInvalido as e:
                raise ApartadoInvalido(e.mensaje)

            total = 0.0
            detalles = []
            for producto_id, cantidad in cantidades.items():
                cursor.execute(
                    """
                    SELECT p.precio, i.id AS inventario_id, COALESCE(i.cantidad, 0) AS stock
                    FROM productos p
                    LEFT JOIN inventarios i ON i.producto_id = p.id AND i.tienda_id = %s
                    WHERE p.id = %s AND p.activo = 1
                    FOR UPDATE
                    """,
                    (tienda_id, producto_id),
                )
                fila = cursor.fetchone()
                if not fila:
                    raise ApartadoInvalido("Uno de los productos no existe o está descontinuado.")
                if fila["stock"] < cantidad:
                    raise ApartadoInvalido("Ya no hay inventario suficiente para uno de los productos.", 409)
                precio = float(fila["precio"])
                total += precio * cantidad
                detalles.append((producto_id, cantidad, precio, fila["inventario_id"]))
            total = round(total, 2)

            anticipo = None
            if datos.get("anticipo"):
                anticipo = _validar_pago(cursor, datos["anticipo"])
                if anticipo[1] > total:
                    raise ApartadoInvalido("El anticipo no puede ser mayor al total del apartado.")

            cursor.execute(
                f"""
                INSERT INTO apartados (tienda_id, cliente_id, usuario_id, fecha_limite, total, observaciones)
                VALUES (%s, %s, %s, DATE(DATE_ADD(NOW(), INTERVAL {VIGENCIA_MESES} MONTH)), %s, %s)
                """,
                (tienda_id, cliente_id, g.turno["usuario_id"], total, observaciones),
            )
            apartado_id = cursor.lastrowid

            for producto_id, cantidad, precio, inventario_id in detalles:
                cursor.execute(
                    """
                    INSERT INTO apartado_detalles (apartado_id, producto_id, cantidad, precio_unitario)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (apartado_id, producto_id, cantidad, precio),
                )
                cursor.execute(
                    "UPDATE inventarios SET cantidad = cantidad - %s WHERE id = %s",
                    (cantidad, inventario_id),
                )

            abonado = 0.0
            if anticipo:
                _registrar_pago(cursor, apartado_id, anticipo[0], anticipo[1])
                abonado = anticipo[1]
                if abonado >= total:
                    cursor.execute("UPDATE apartados SET estado = 'liquidado' WHERE id = %s", (apartado_id,))
    except ApartadoInvalido as e:
        return jsonify(error=e.mensaje), e.status

    return jsonify(
        mensaje=f"Apartado #{apartado_id} registrado.",
        apartado_id=apartado_id,
        total=total,
        abonado=abonado,
        saldo=round(total - abonado, 2),
    ), 201


@apartados_bp.route("/apartados/<int:apartado_id>/abonar", methods=["POST"])
@turno_required
def abonar(apartado_id):
    """Registra un abono (cualquier tienda, cualquier método). Si liquida el saldo, el apartado queda 'liquidado'."""
    datos = request.get_json(silent=True) or {}

    try:
        with db_cursor(commit=True) as cursor:
            apartado = _apartado_para_cobro(cursor, apartado_id)
            if apartado["saldo"] <= 0:
                raise ApartadoInvalido("Este apartado ya está pagado; solo falta entregarlo.")

            metodo_pago_id, monto, _ = _validar_pago(cursor, datos)
            if monto > apartado["saldo"]:
                raise ApartadoInvalido(
                    f"El abono no puede ser mayor al saldo pendiente (${apartado['saldo']:,.2f})."
                )

            _registrar_pago(cursor, apartado_id, metodo_pago_id, monto)
            saldo = round(apartado["saldo"] - monto, 2)
            estado = "liquidado" if saldo <= 0 else apartado["estado"]
            if estado != apartado["estado"]:
                cursor.execute("UPDATE apartados SET estado = %s WHERE id = %s", (estado, apartado_id))
    except ApartadoInvalido as e:
        return jsonify(error=e.mensaje), e.status

    return jsonify(
        mensaje="Abono registrado." + (" El apartado quedó pagado." if saldo <= 0 else ""),
        apartado_id=apartado_id,
        monto_abonado=monto,
        saldo_restante=saldo,
        estado=estado,
    ), 200


@apartados_bp.route("/apartados/<int:apartado_id>/entregar", methods=["POST"])
@turno_required
def entregar(apartado_id):
    """El cliente se lleva la mercancía. Si queda saldo, se cobra aquí mismo con `pago`.

    pago = {metodo_pago_id, recibido}: en efectivo puede ser mayor al saldo (se regresa cambio);
    se guarda como abono solo el saldo, así el corte de caja cuadra con el efectivo real.
    """
    datos = request.get_json(silent=True) or {}
    cambio = 0.0

    try:
        with db_cursor(commit=True) as cursor:
            apartado = _apartado_para_cobro(cursor, apartado_id)
            if apartado["tienda_id"] != g.turno["tienda_id"]:
                raise ApartadoInvalido("La mercancía de este apartado está en otra tienda.", 403)

            if apartado["saldo"] > 0:
                if not datos.get("pago"):
                    raise ApartadoInvalido(
                        f"Falta pagar ${apartado['saldo']:,.2f} para entregar el apartado."
                    )
                metodo_pago_id, recibido, metodo = _validar_pago(cursor, datos["pago"], "recibido")
                if recibido < apartado["saldo"]:
                    raise ApartadoInvalido(
                        f"El pago no cubre el saldo pendiente (${apartado['saldo']:,.2f})."
                    )
                if recibido > apartado["saldo"] and metodo != "efectivo":
                    raise ApartadoInvalido("Solo en efectivo se puede recibir más del saldo (para dar cambio).")

                _registrar_pago(cursor, apartado_id, metodo_pago_id, apartado["saldo"])
                cambio = round(recibido - apartado["saldo"], 2)

            cursor.execute(
                "UPDATE apartados SET estado = 'entregado', fecha_entrega = NOW() WHERE id = %s",
                (apartado_id,),
            )
    except ApartadoInvalido as e:
        return jsonify(error=e.mensaje), e.status

    return jsonify(mensaje=f"Apartado #{apartado_id} entregado.", apartado_id=apartado_id, cambio=cambio), 200
