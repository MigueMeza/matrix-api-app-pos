"""Consulta de ventas para /admin (solo lectura): tickets filtrados por fecha, tienda, vendedor y método.

Las rutas se registran en admin_bp, así que heredan su before_request (solo super_admin).
Fechas: el cliente manda `desde`/`hasta` en ISO 8601 con zona (su medianoche local ya convertida);
la base guarda UTC, así que se comparan en UTC. `hasta` es exclusivo.
"""
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

from ..db import db_cursor
from ..permisos import Rol
from .admin import admin_bp

# Tope de tickets por consulta: el resumen sí cuenta todos los que cumplen el filtro
LIMITE_TICKETS = 1000


def _fecha_utc(texto, por_defecto):
    """ISO 8601 (con zona) → datetime UTC sin zona, como lo guarda MySQL."""
    if not texto:
        return por_defecto
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc).replace(tzinfo=None)


def _entero(nombre):
    valor = request.args.get(nombre, "").strip()
    return int(valor) if valor.isdigit() else None


def _rango():
    """(desde, hasta) en UTC; por defecto los últimos 7 días."""
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    desde = _fecha_utc(request.args.get("desde"), ahora - timedelta(days=7))
    hasta = _fecha_utc(request.args.get("hasta"), ahora + timedelta(minutes=1))
    return desde, hasta


@admin_bp.route("/ventas/filtros", methods=["GET"])
def ventas_filtros():
    """Opciones para los filtros: todas las tiendas (también inactivas: tienen historial), quienes venden y métodos."""
    with db_cursor() as cursor:
        cursor.execute("SELECT id, nombre, activo FROM tiendas ORDER BY nombre")
        tiendas = cursor.fetchall()
        cursor.execute(
            "SELECT id, nombre FROM usuarios WHERE rol IN (%s, %s) ORDER BY nombre",
            (Rol.VENDEDOR.value, Rol.SUPER_ADMIN.value),
        )
        vendedores = cursor.fetchall()
        cursor.execute("SELECT id, nombre FROM metodos_pago ORDER BY id")
        metodos_pago = cursor.fetchall()

    for tienda in tiendas:
        tienda["activo"] = bool(tienda["activo"])
    return jsonify(tiendas=tiendas, vendedores=vendedores, metodos_pago=metodos_pago), 200


@admin_bp.route("/ventas", methods=["GET"])
def ventas_listar():
    """Tickets que cumplen los filtros (los más recientes primero) y el resumen de todos ellos.

    Filtros: desde, hasta, tienda_id, usuario_id, metodo_pago_id.
    `ticket` busca un ticket por número en cualquier fecha e ignora los demás filtros.
    """
    ticket = _entero("ticket")
    condiciones, parametros = [], []

    if ticket:
        condiciones.append("v.id = %s")
        parametros.append(ticket)
    else:
        desde, hasta = _rango()
        if desde is None or hasta is None:
            return jsonify(error="Fechas inválidas."), 400
        condiciones += ["v.fecha >= %s", "v.fecha < %s"]
        parametros += [desde, hasta]

        for campo, columna in (("tienda_id", "v.tienda_id"), ("usuario_id", "v.usuario_id")):
            valor = _entero(campo)
            if valor:
                condiciones.append(f"{columna} = %s")
                parametros.append(valor)

        metodo_pago_id = _entero("metodo_pago_id")
        if metodo_pago_id:
            condiciones.append(
                "EXISTS (SELECT 1 FROM venta_pagos f WHERE f.venta_id = v.id AND f.metodo_pago_id = %s)"
            )
            parametros.append(metodo_pago_id)

    where = " AND ".join(condiciones)

    with db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT v.id, v.fecha, v.tienda_id, t.nombre AS tienda_nombre,
                   v.usuario_id, u.nombre AS usuario_nombre, v.total,
                   (SELECT COALESCE(SUM(d.cantidad), 0) FROM detalle_ventas d WHERE d.venta_id = v.id) AS piezas,
                   (SELECT p.id FROM pedidos p WHERE p.venta_id = v.id LIMIT 1) AS pedido_id
            FROM ventas v
            JOIN tiendas t ON t.id = v.tienda_id
            JOIN usuarios u ON u.id = v.usuario_id
            WHERE {where}
            ORDER BY v.fecha DESC, v.id DESC
            LIMIT {LIMITE_TICKETS + 1}
            """,
            parametros,
        )
        ventas = cursor.fetchall()
        limite_alcanzado = len(ventas) > LIMITE_TICKETS
        ventas = ventas[:LIMITE_TICKETS]

        pagos_por_venta = {}
        if ventas:
            ids = [v["id"] for v in ventas]
            cursor.execute(
                f"""
                SELECT vp.venta_id, m.nombre AS metodo, vp.monto
                FROM venta_pagos vp
                JOIN metodos_pago m ON m.id = vp.metodo_pago_id
                WHERE vp.venta_id IN ({", ".join(["%s"] * len(ids))})
                ORDER BY vp.id
                """,
                ids,
            )
            for p in cursor.fetchall():
                pagos_por_venta.setdefault(p.pop("venta_id"), []).append({**p, "monto": float(p["monto"])})

        # Resumen de TODOS los tickets del filtro, no solo de los que se muestran
        cursor.execute(
            f"""
            SELECT COUNT(*) AS tickets, COALESCE(SUM(v.total), 0) AS total,
                   COALESCE(SUM((SELECT SUM(d.cantidad) FROM detalle_ventas d WHERE d.venta_id = v.id)), 0) AS piezas
            FROM ventas v
            WHERE {where}
            """,
            parametros,
        )
        resumen = cursor.fetchone()
        cursor.execute(
            f"""
            SELECT m.nombre AS metodo, SUM(vp.monto) AS monto
            FROM ventas v
            JOIN venta_pagos vp ON vp.venta_id = v.id
            JOIN metodos_pago m ON m.id = vp.metodo_pago_id
            WHERE {where}
            GROUP BY m.id, m.nombre
            ORDER BY m.id
            """,
            parametros,
        )
        por_metodo = [{**m, "monto": float(m["monto"])} for m in cursor.fetchall()]

    for v in ventas:
        v["total"] = float(v["total"])
        v["piezas"] = int(v["piezas"])
        v["pagos"] = pagos_por_venta.get(v["id"], [])

    return jsonify(
        ventas=ventas,
        limite_alcanzado=limite_alcanzado,
        resumen={
            "tickets": resumen["tickets"],
            "total": float(resumen["total"]),
            "piezas": int(resumen["piezas"]),
            "por_metodo": por_metodo,
        },
    ), 200


@admin_bp.route("/ventas/<int:venta_id>", methods=["GET"])
def ventas_detalle(venta_id):
    """Ticket completo: productos, pagos y, si vino de un pedido, cuál."""
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT v.id, v.fecha, v.total, v.tienda_id, t.nombre AS tienda_nombre,
                   v.usuario_id, u.nombre AS usuario_nombre,
                   (SELECT p.id FROM pedidos p WHERE p.venta_id = v.id LIMIT 1) AS pedido_id
            FROM ventas v
            JOIN tiendas t ON t.id = v.tienda_id
            JOIN usuarios u ON u.id = v.usuario_id
            WHERE v.id = %s
            """,
            (venta_id,),
        )
        venta = cursor.fetchone()
        if not venta:
            return jsonify(error="El ticket no existe."), 404

        cursor.execute(
            """
            SELECT d.producto_id, p.codigo_barras, p.nombre, p.talla, p.color,
                   d.cantidad, d.precio_unitario, d.subtotal
            FROM detalle_ventas d
            JOIN productos p ON p.id = d.producto_id
            WHERE d.venta_id = %s
            ORDER BY d.id
            """,
            (venta_id,),
        )
        items = cursor.fetchall()

        cursor.execute(
            """
            SELECT m.nombre AS metodo, vp.monto
            FROM venta_pagos vp
            JOIN metodos_pago m ON m.id = vp.metodo_pago_id
            WHERE vp.venta_id = %s
            ORDER BY vp.id
            """,
            (venta_id,),
        )
        pagos = cursor.fetchall()

    venta["total"] = float(venta["total"])
    for i in items:
        i["precio_unitario"] = float(i["precio_unitario"])
        i["subtotal"] = float(i["subtotal"])
    for p in pagos:
        p["monto"] = float(p["monto"])

    return jsonify(venta=venta, items=items, pagos=pagos), 200
