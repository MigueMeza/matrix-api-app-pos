import pymysql
from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash

from ..auth import requiere_rol
from ..db import db_cursor
from ..permisos import Rol

caja_bp = Blueprint("caja", __name__, url_prefix="/caja")


def _vendedores_disponibles(cursor):
    """Vendedores activos sin un turno abierto en ninguna tienda."""
    cursor.execute(
        """
        SELECT u.id, u.nombre, u.usuario_login
        FROM usuarios u
        WHERE u.rol = %s AND u.activo = 1
          AND NOT EXISTS (
              SELECT 1 FROM turnos_caja t
              WHERE t.usuario_id = u.id AND t.estado = 'abierto'
          )
        ORDER BY u.nombre
        """,
        (Rol.VENDEDOR.value,),
    )
    return cursor.fetchall()


def _tiendas_activas(cursor):
    cursor.execute("SELECT id, nombre FROM tiendas WHERE activo = 1 ORDER BY nombre")
    return cursor.fetchall()


def _turnos_abiertos(cursor):
    """Cajas abiertas en cualquier tienda: si su terminal se cerró o se descompuso, se pueden retomar."""
    cursor.execute(
        """
        SELECT t.id, t.tienda_id, ti.nombre AS tienda_nombre, u.nombre AS usuario_nombre,
               t.fecha_apertura, t.fondo_inicial
        FROM turnos_caja t
        JOIN tiendas ti ON ti.id = t.tienda_id
        JOIN usuarios u ON u.id = t.usuario_id
        WHERE t.estado = 'abierto'
        ORDER BY t.fecha_apertura
        """
    )
    turnos = cursor.fetchall()
    for turno in turnos:
        turno["fondo_inicial"] = float(turno["fondo_inicial"])
    return turnos


@caja_bp.route("/abrir", methods=["GET"])
@requiere_rol(Rol.SUPER_ADMIN, Rol.SUPERVISOR)
def abrir_formulario():
    puede_vender_el_mismo = session.get("rol") == Rol.SUPER_ADMIN.value

    with db_cursor() as cursor:
        vendedores = _vendedores_disponibles(cursor)
        tiendas = _tiendas_activas(cursor)
        turnos_abiertos = _turnos_abiertos(cursor)

    return jsonify(
        vendedores=vendedores,
        tiendas=tiendas,
        puede_vender_el_mismo=puede_vender_el_mismo,
        turnos_abiertos=turnos_abiertos,
    ), 200


@caja_bp.route("/retomar", methods=["POST"])
@requiere_rol(Rol.SUPER_ADMIN, Rol.SUPERVISOR)
def retomar():
    """Un supervisor/super_admin pasa a esta terminal una caja que quedó abierta en otra
    (o en esta, si la app se cerró y se perdió la sesión). Igual que al abrir caja, la sesión
    de usuario se reemplaza por el turno.
    """
    datos = request.get_json(silent=True) or {}
    try:
        turno_id = int(datos.get("turno_id"))
    except (TypeError, ValueError):
        return jsonify(error="Indica la caja que quieres retomar."), 400

    with db_cursor() as cursor:
        cursor.execute("SELECT id FROM turnos_caja WHERE id = %s AND estado = 'abierto'", (turno_id,))
        if not cursor.fetchone():
            return jsonify(error="Esa caja ya no está abierta."), 409

    session.clear()
    session["turno_id"] = turno_id

    return jsonify(mensaje="Caja retomada.", turno_id=turno_id), 200


@caja_bp.route("/abrir", methods=["POST"])
@requiere_rol(Rol.SUPER_ADMIN, Rol.SUPERVISOR)
def abrir():
    puede_vender_el_mismo = session.get("rol") == Rol.SUPER_ADMIN.value

    datos = request.get_json(silent=True) or {}
    modo = datos.get("modo", "asignar")
    tienda_id = datos.get("tienda_id")
    fondo_inicial = datos.get("fondo_inicial")

    if modo == "yo_mismo" and not puede_vender_el_mismo:
        return jsonify(
            error="Un supervisor no puede abrir su propia caja para vender; debe asignar un vendedor."
        ), 400
    elif modo == "yo_mismo":
        usuario_id_vendedor = session["usuario_id"]
    else:
        usuario_id_vendedor = datos.get("usuario_id")

    try:
        tienda_id = int(tienda_id) if tienda_id is not None else None
        fondo_inicial = float(fondo_inicial) if fondo_inicial is not None else None
        usuario_id_vendedor = int(usuario_id_vendedor) if usuario_id_vendedor is not None else None
    except (TypeError, ValueError):
        return jsonify(error="Completa todos los campos con valores válidos."), 400

    if not usuario_id_vendedor or not tienda_id or fondo_inicial is None or fondo_inicial < 0:
        return jsonify(error="Completa todos los campos con valores válidos."), 400

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            SELECT ti.nombre AS tienda_nombre
            FROM turnos_caja t
            JOIN tiendas ti ON ti.id = t.tienda_id
            WHERE t.usuario_id = %s AND t.estado = 'abierto'
            FOR UPDATE
            """,
            (usuario_id_vendedor,),
        )
        turno_existente = cursor.fetchone()

        if turno_existente:
            return jsonify(
                error=f"Ya hay una caja abierta para ese usuario en {turno_existente['tienda_nombre']}."
            ), 409

        try:
            cursor.execute(
                """
                INSERT INTO turnos_caja (tienda_id, usuario_id, abierto_por, fondo_inicial)
                VALUES (%s, %s, %s, %s)
                """,
                (tienda_id, usuario_id_vendedor, session["usuario_id"], fondo_inicial),
            )
            nuevo_turno_id = cursor.lastrowid
        except pymysql.err.IntegrityError:
            return jsonify(error="Ya hay una caja abierta para ese usuario en otra tienda."), 409

    session.clear()
    session["turno_id"] = nuevo_turno_id

    return jsonify(mensaje="Caja abierta exitosamente.", turno_id=nuevo_turno_id), 201


@caja_bp.route("/corte", methods=["POST"])
def corte():
    turno_id = session.get("turno_id")
    if not turno_id:
        return jsonify(error="No hay una caja abierta en esta terminal."), 400

    datos = request.get_json(silent=True) or {}
    usuario_login = (datos.get("usuario_login") or "").strip()
    password = datos.get("password") or ""
    notas = (datos.get("notas") or "").strip() or None

    try:
        fondo_final = float(datos.get("fondo_final"))
    except (TypeError, ValueError):
        return jsonify(error="Captura el efectivo contado."), 400
    if fondo_final < 0:
        return jsonify(error="El efectivo contado no puede ser negativo."), 400

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nombre, password_hash FROM usuarios
            WHERE usuario_login = %s AND rol IN (%s, %s) AND activo = 1
            """,
            (usuario_login, Rol.SUPER_ADMIN.value, Rol.SUPERVISOR.value),
        )
        autorizador = cursor.fetchone()

    if not autorizador or not autorizador["password_hash"] or not check_password_hash(
        autorizador["password_hash"], password
    ):
        return jsonify(error="Usuario o contraseña incorrectos."), 401

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT * FROM turnos_caja WHERE id = %s AND estado = 'abierto' FOR UPDATE",
            (turno_id,),
        )
        turno = cursor.fetchone()
        if not turno:
            session.pop("turno_id", None)
            return jsonify(error="Esta caja ya fue cerrada."), 409

        cursor.execute(
            """
            SELECT COALESCE(SUM(vp.monto), 0) AS total
            FROM venta_pagos vp
            JOIN ventas v ON v.id = vp.venta_id
            JOIN metodos_pago mp ON mp.id = vp.metodo_pago_id
            WHERE v.turno_id = %s AND mp.nombre = 'efectivo'
            """,
            (turno_id,),
        )
        efectivo_ventas = float(cursor.fetchone()["total"])

        cursor.execute(
            """
            SELECT COALESCE(SUM(ap.monto), 0) AS total
            FROM apartado_pagos ap
            JOIN metodos_pago mp ON mp.id = ap.metodo_pago_id
            WHERE ap.turno_id = %s AND mp.nombre = 'efectivo'
            """,
            (turno_id,),
        )
        efectivo_apartados = float(cursor.fetchone()["total"])

        efectivo_vendido = efectivo_ventas + efectivo_apartados
        efectivo_esperado = float(turno["fondo_inicial"]) + efectivo_vendido
        diferencia = fondo_final - efectivo_esperado

        cursor.execute(
            """
            UPDATE turnos_caja
            SET estado = 'cerrado', fondo_final = %s, cerrado_por = %s,
                fecha_cierre = NOW(), notas_cierre = %s
            WHERE id = %s
            """,
            (fondo_final, autorizador["id"], notas, turno_id),
        )

    session.pop("turno_id", None)

    return jsonify(
        fondo_inicial=float(turno["fondo_inicial"]),
        efectivo_ventas=efectivo_ventas,
        efectivo_abonos=efectivo_apartados,
        efectivo_vendido=efectivo_vendido,
        efectivo_esperado=efectivo_esperado,
        fondo_final=fondo_final,
        diferencia=diferencia,
        cerrado_por=autorizador["nombre"],
    ), 200
