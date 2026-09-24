"""Resumen del negocio para el inicio de /admin: valor del inventario, ventas, pendientes y equipo.

Las rutas se registran en admin_bp, así que heredan su before_request (solo super_admin).
"""
from datetime import datetime, timezone

from flask import jsonify, request

from ..db import db_cursor
from ..permisos import Rol
from .admin import admin_bp
from .admin_ventas import _fecha_utc
from .apartados import SQL_SITUACION

# Mismo umbral que la vista de inventarios del POS
POCAS_EXISTENCIAS = 3


def _f(valor):
    return float(valor or 0)


# Valor del inventario (solo productos y tiendas activos). La inversión y la utilidad cuentan únicamente las
# piezas con precio de compra: los productos dados de alta antes de existir esa columna no lo tienen, y
# sumarlos como costo cero inflaría la utilidad. piezas_sin_costo dice cuántas quedan fuera.
SQL_INVENTARIO = """
    SELECT COALESCE(SUM(i.cantidad), 0) AS piezas,
           COALESCE(SUM(i.cantidad * p.precio), 0) AS valor_venta,
           COALESCE(SUM(CASE WHEN p.precio_compra IS NOT NULL THEN i.cantidad * p.precio_compra END), 0) AS inversion,
           COALESCE(SUM(CASE WHEN p.precio_compra IS NOT NULL THEN i.cantidad * p.precio END), 0) AS valor_venta_con_costo,
           COALESCE(SUM(CASE WHEN p.precio_compra IS NULL THEN i.cantidad END), 0) AS piezas_sin_costo
    FROM inventarios i
    JOIN productos p ON p.id = i.producto_id
    JOIN tiendas t ON t.id = i.tienda_id
    WHERE p.activo = 1 AND t.activo = 1
"""


def _valor(fila):
    """Inversión, valor de venta y utilidad (monto y % sobre la inversión)."""
    inversion = _f(fila["inversion"])
    venta_con_costo = _f(fila["valor_venta_con_costo"])
    utilidad = venta_con_costo - inversion
    return {
        "piezas": int(fila["piezas"]),
        "piezas_sin_costo": int(fila["piezas_sin_costo"]),
        "inversion": inversion,
        "valor_venta": _f(fila["valor_venta"]),
        "valor_venta_con_costo": venta_con_costo,
        "utilidad": utilidad,
        "utilidad_porcentaje": (utilidad / inversion * 100) if inversion > 0 else None,
    }


@admin_bp.route("/resumen", methods=["GET"])
def resumen():
    """Todo el tablero de inicio en una consulta.

    `inicio_hoy` / `inicio_mes`: medianoche local del cliente en ISO 8601 con zona (la base guarda UTC).
    """
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    inicio_hoy = _fecha_utc(request.args.get("inicio_hoy"), ahora.replace(hour=0, minute=0, second=0, microsecond=0))
    inicio_mes = _fecha_utc(request.args.get("inicio_mes"), inicio_hoy.replace(day=1) if inicio_hoy else None)
    if inicio_hoy is None or inicio_mes is None:
        return jsonify(error="Fechas inválidas."), 400

    with db_cursor() as cursor:
        # ---------- Inventario ----------
        cursor.execute(SQL_INVENTARIO)
        inventario = _valor(cursor.fetchone())

        cursor.execute(
            SQL_INVENTARIO.replace("SELECT ", "SELECT t.id AS tienda_id, t.nombre AS tienda, ", 1)
            + " GROUP BY t.id, t.nombre ORDER BY t.nombre"
        )
        por_tienda = [{"tienda_id": f["tienda_id"], "tienda": f["tienda"], **_valor(f)} for f in cursor.fetchall()]

        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT p.id) AS productos_activos,
                   COALESCE(SUM(i.cantidad = 0), 0) AS agotados,
                   COALESCE(SUM(i.cantidad BETWEEN 1 AND {POCAS_EXISTENCIAS}), 0) AS pocas_existencias
            FROM productos p
            LEFT JOIN inventarios i ON i.producto_id = p.id
                 AND i.tienda_id IN (SELECT id FROM tiendas WHERE activo = 1)
            WHERE p.activo = 1
            """
        )
        existencias = {k: int(v) for k, v in cursor.fetchone().items()}

        # ---------- Ventas ----------
        ventas = {}
        for periodo, desde in (("hoy", inicio_hoy), ("mes", inicio_mes)):
            cursor.execute(
                "SELECT COUNT(*) AS tickets, COALESCE(SUM(total), 0) AS total FROM ventas WHERE fecha >= %s",
                (desde,),
            )
            fila = cursor.fetchone()
            ventas[periodo] = {"tickets": fila["tickets"], "total": _f(fila["total"])}

        # ---------- Operación: lo que está pendiente ----------
        cursor.execute(
            """
            SELECT t.id, ti.nombre AS tienda, u.nombre AS vendedor, t.fecha_apertura
            FROM turnos_caja t
            JOIN tiendas ti ON ti.id = t.tienda_id
            JOIN usuarios u ON u.id = t.usuario_id
            WHERE t.estado = 'abierto'
            ORDER BY t.fecha_apertura
            """
        )
        cajas_abiertas = cursor.fetchall()

        cursor.execute(
            """
            SELECT COALESCE(SUM(estado = 'pendiente'), 0) AS pendientes,
                   COALESCE(SUM(estado = 'disponible'), 0) AS disponibles,
                   COALESCE(SUM(estado = 'pendiente' AND EXISTS (
                       SELECT 1 FROM pedido_detalles d WHERE d.pedido_id = pedidos.id AND d.producto_id IS NULL
                   )), 0) AS por_asignar
            FROM pedidos
            """
        )
        pedidos = {k: int(v) for k, v in cursor.fetchone().items()}

        cursor.execute(
            f"""
            SELECT situacion, COUNT(*) AS cantidad, COALESCE(SUM(saldo), 0) AS saldo
            FROM (
                SELECT {SQL_SITUACION} AS situacion,
                       a.total - COALESCE((SELECT SUM(p.monto) FROM apartado_pagos p WHERE p.apartado_id = a.id), 0) AS saldo
                FROM apartados a
            ) x
            WHERE situacion IN ('vigente', 'expirado')
            GROUP BY situacion
            """
        )
        apartados = {"vigentes": {"cantidad": 0, "saldo": 0.0}, "expirados": {"cantidad": 0, "saldo": 0.0}}
        for fila in cursor.fetchall():
            clave = "vigentes" if fila["situacion"] == "vigente" else "expirados"
            apartados[clave] = {"cantidad": fila["cantidad"], "saldo": _f(fila["saldo"])}

        # ---------- Equipo ----------
        cursor.execute("SELECT COALESCE(SUM(activo = 1), 0) AS activas, COALESCE(SUM(activo = 0), 0) AS inactivas FROM tiendas")
        tiendas = {k: int(v) for k, v in cursor.fetchone().items()}

        cursor.execute("SELECT rol, COUNT(*) AS n FROM usuarios WHERE activo = 1 GROUP BY rol")
        por_rol = {f["rol"]: f["n"] for f in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) AS n FROM usuarios WHERE activo = 0")
        empleados = {
            "supervisores": por_rol.get(Rol.SUPERVISOR.value, 0),
            "cajeros": por_rol.get(Rol.VENDEDOR.value, 0),
            "super_admins": por_rol.get(Rol.SUPER_ADMIN.value, 0),
            "inactivos": cursor.fetchone()["n"],
        }
        empleados["activos"] = empleados["supervisores"] + empleados["cajeros"] + empleados["super_admins"]

    return jsonify(
        inventario={**inventario, **existencias, "pocas_existencias_umbral": POCAS_EXISTENCIAS},
        por_tienda=por_tienda,
        ventas=ventas,
        cajas_abiertas=cajas_abiertas,
        pedidos=pedidos,
        apartados=apartados,
        tiendas=tiendas,
        empleados=empleados,
    ), 200
