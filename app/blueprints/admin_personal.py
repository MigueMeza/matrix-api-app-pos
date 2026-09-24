"""Personal (usuarios) para /admin: alta con usuario y NIP generados, edición, permisos, baja y reseteo de NIP.

Las rutas se registran en admin_bp, así que heredan su before_request (solo super_admin).
El NIP solo se devuelve en la respuesta del alta o del reseteo: en la base queda su hash.
Un usuario con historial (ventas, turnos, pedidos, apartados) no se puede eliminar: se deshabilita.
"""
import pymysql
from flask import jsonify, request, session
from werkzeug.security import generate_password_hash

from ..credenciales import nuevo_nip, prefijo_usuario, siguiente_usuario
from ..db import db_cursor
from ..permisos import Rol
from .admin import admin_bp

ROLES = [Rol.VENDEDOR.value, Rol.SUPERVISOR.value, Rol.SUPER_ADMIN.value]

# ¿Aparece en algún registro histórico? (bloquea eliminarlo)
SQL_HISTORIAL_USUARIO = """
    EXISTS (SELECT 1 FROM ventas WHERE usuario_id = u.id)
    OR EXISTS (SELECT 1 FROM turnos_caja WHERE u.id IN (usuario_id, abierto_por, cerrado_por))
    OR EXISTS (SELECT 1 FROM apartados WHERE usuario_id = u.id)
    OR EXISTS (SELECT 1 FROM apartado_pagos WHERE usuario_id = u.id)
    OR EXISTS (SELECT 1 FROM pedidos WHERE usuario_id = u.id)
"""


class PersonalInvalido(Exception):
    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


def _respuesta_error(e):
    return jsonify(error=e.mensaje), e.status


def _usuario(cursor, usuario_id):
    cursor.execute(
        f"""
        SELECT u.id, u.nombre, u.usuario_login, u.rol, u.activo, ({SQL_HISTORIAL_USUARIO}) AS tiene_historial,
               EXISTS (SELECT 1 FROM turnos_caja t WHERE t.usuario_id = u.id AND t.estado = 'abierto') AS caja_abierta
        FROM usuarios u WHERE u.id = %s FOR UPDATE
        """,
        (usuario_id,),
    )
    usuario = cursor.fetchone()
    if not usuario:
        raise PersonalInvalido("El usuario no existe.", 404)
    return usuario


def _no_es_uno_mismo(usuario, accion):
    if usuario["id"] == session.get("usuario_id"):
        raise PersonalInvalido(f"No puedes {accion} tu propio usuario.")


def _no_deja_sin_super_admin(cursor, usuario):
    """Siempre debe quedar al menos un super admin activo (si no, nadie podría entrar al panel)."""
    if usuario["rol"] != Rol.SUPER_ADMIN.value or not usuario["activo"]:
        return
    cursor.execute("SELECT COUNT(*) AS n FROM usuarios WHERE rol = %s AND activo = 1", (Rol.SUPER_ADMIN.value,))
    if cursor.fetchone()["n"] <= 1:
        raise PersonalInvalido("Es el único super administrador activo: debe quedar al menos uno.")


def _tienda_activa(cursor, tienda_id):
    try:
        tienda_id = int(tienda_id)
    except (TypeError, ValueError):
        raise PersonalInvalido("Elige la tienda del empleado.")
    cursor.execute("SELECT id FROM tiendas WHERE id = %s AND activo = 1", (tienda_id,))
    if not cursor.fetchone():
        raise PersonalInvalido("La tienda no existe o está inactiva.")
    return tienda_id


def _rol(valor):
    if valor not in ROLES:
        raise PersonalInvalido("El nivel de permisos no es válido.")
    return valor


@admin_bp.route("/usuarios", methods=["GET"])
def usuarios_listar():
    with db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT u.id, u.nombre, u.usuario_login, u.rol, u.activo, u.tienda_id, t.nombre AS tienda,
                   u.password_hash IS NOT NULL AS tiene_nip,
                   ({SQL_HISTORIAL_USUARIO}) AS tiene_historial,
                   EXISTS (SELECT 1 FROM turnos_caja c WHERE c.usuario_id = u.id AND c.estado = 'abierto') AS caja_abierta
            FROM usuarios u
            JOIN tiendas t ON t.id = u.tienda_id
            ORDER BY u.activo DESC, FIELD(u.rol, 'super_admin', 'supervisor', 'vendedor'), u.nombre
            """
        )
        usuarios = cursor.fetchall()
        cursor.execute("SELECT id, nombre FROM tiendas WHERE activo = 1 ORDER BY nombre")
        tiendas = cursor.fetchall()

    actual = session.get("usuario_id")
    for u in usuarios:
        for campo in ("activo", "tiene_nip", "tiene_historial", "caja_abierta"):
            u[campo] = bool(u[campo])
        u["es_actual"] = u["id"] == actual

    return jsonify(usuarios=usuarios, tiendas=tiendas, roles=ROLES), 200


@admin_bp.route("/usuarios", methods=["POST"])
def usuarios_crear():
    """Alta: el usuario (ANPE1...) y el NIP se generan aquí. El NIP solo viaja en esta respuesta."""
    datos = request.get_json(silent=True) or {}
    nombres = " ".join((datos.get("nombres") or "").split())
    paterno = " ".join((datos.get("apellido_paterno") or "").split())
    materno = " ".join((datos.get("apellido_materno") or "").split())

    try:
        if not nombres or not paterno:
            raise PersonalInvalido("Captura el nombre y el apellido paterno.")
        prefijo = prefijo_usuario(nombres, paterno)
        if len(prefijo) < 2:
            raise PersonalInvalido("El nombre y el apellido deben tener letras.")
        rol = _rol(datos.get("rol"))
        nombre = " ".join(p for p in (nombres, paterno, materno) if p)[:150]
        nip = nuevo_nip()

        # Dos altas al mismo tiempo podrían calcular el mismo número: el índice único lo rechaza y se reintenta
        for _ in range(5):
            try:
                with db_cursor(commit=True) as cursor:
                    tienda_id = _tienda_activa(cursor, datos.get("tienda_id"))
                    usuario_login = siguiente_usuario(cursor, prefijo)
                    cursor.execute(
                        """
                        INSERT INTO usuarios (tienda_id, nombre, usuario_login, password_hash, rol)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (tienda_id, nombre, usuario_login, generate_password_hash(nip), rol),
                    )
                    usuario_id = cursor.lastrowid
                break
            except pymysql.err.IntegrityError:
                continue
        else:
            raise PersonalInvalido("No se pudo generar el usuario; intenta de nuevo.", 409)
    except PersonalInvalido as e:
        return _respuesta_error(e)

    return jsonify(
        mensaje="Empleado registrado.",
        usuario={"id": usuario_id, "nombre": nombre, "usuario_login": usuario_login, "rol": rol},
        nip=nip,
    ), 201


@admin_bp.route("/usuarios/<int:usuario_id>", methods=["PUT"])
def usuarios_editar(usuario_id):
    """Nombre, tienda y nivel de permisos. El usuario (ANPE1) no cambia aunque cambie el nombre."""
    datos = request.get_json(silent=True) or {}
    try:
        with db_cursor(commit=True) as cursor:
            usuario = _usuario(cursor, usuario_id)
            nombre = " ".join((datos.get("nombre") or "").split())
            if not nombre:
                raise PersonalInvalido("El nombre no puede quedar vacío.")
            tienda_id = _tienda_activa(cursor, datos.get("tienda_id"))
            rol = _rol(datos.get("rol"))

            if rol != usuario["rol"]:
                _no_es_uno_mismo(usuario, "cambiar los permisos de")
                _no_deja_sin_super_admin(cursor, usuario)

            cursor.execute(
                "UPDATE usuarios SET nombre = %s, tienda_id = %s, rol = %s WHERE id = %s",
                (nombre[:150], tienda_id, rol, usuario_id),
            )
    except PersonalInvalido as e:
        return _respuesta_error(e)

    return jsonify(mensaje="Empleado actualizado."), 200


@admin_bp.route("/usuarios/<int:usuario_id>/estado", methods=["POST"])
def usuarios_estado(usuario_id):
    """Deshabilitar (ya no entra ni aparece para abrir caja) o volver a habilitar."""
    activo = bool((request.get_json(silent=True) or {}).get("activo"))
    try:
        with db_cursor(commit=True) as cursor:
            usuario = _usuario(cursor, usuario_id)
            if not activo:
                _no_es_uno_mismo(usuario, "deshabilitar")
                _no_deja_sin_super_admin(cursor, usuario)
                if usuario["caja_abierta"]:
                    raise PersonalInvalido("Tiene una caja abierta: primero hay que hacerle el corte.", 409)
            cursor.execute("UPDATE usuarios SET activo = %s WHERE id = %s", (activo, usuario_id))
    except PersonalInvalido as e:
        return _respuesta_error(e)

    return jsonify(mensaje="Empleado habilitado." if activo else "Empleado deshabilitado."), 200


@admin_bp.route("/usuarios/<int:usuario_id>/nip", methods=["POST"])
def usuarios_resetear_nip(usuario_id):
    """Genera un NIP nuevo (por si lo olvidó). El anterior deja de servir. Solo viaja en esta respuesta."""
    nip = nuevo_nip()
    try:
        with db_cursor(commit=True) as cursor:
            usuario = _usuario(cursor, usuario_id)
            cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s",
                           (generate_password_hash(nip), usuario_id))
    except PersonalInvalido as e:
        return _respuesta_error(e)

    return jsonify(mensaje="NIP reseteado.", usuario_login=usuario["usuario_login"], nip=nip), 200


@admin_bp.route("/usuarios/<int:usuario_id>", methods=["DELETE"])
def usuarios_eliminar(usuario_id):
    """Solo sin historial (p. ej. dado de alta por error). Con historial hay que deshabilitarlo."""
    try:
        with db_cursor(commit=True) as cursor:
            usuario = _usuario(cursor, usuario_id)
            _no_es_uno_mismo(usuario, "eliminar")
            _no_deja_sin_super_admin(cursor, usuario)
            if usuario["tiene_historial"]:
                raise PersonalInvalido(
                    "Tiene ventas, cajas, pedidos o apartados registrados: no se puede eliminar sin perder ese "
                    "historial. Deshabilítalo en su lugar.", 409)
            cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    except PersonalInvalido as e:
        return _respuesta_error(e)

    return jsonify(mensaje="Empleado eliminado."), 200
