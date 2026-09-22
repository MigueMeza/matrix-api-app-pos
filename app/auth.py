from functools import wraps
from flask import g, jsonify, request, session
from .db import db_cursor


def requiere_rol(*roles):
    """Verifica que el usuario autenticado tenga alguno de los roles permitidos.
    
    Devuelve 401 si no está autenticado o 403 si no tiene permisos suficientes.
    """
    valores = {r.value if hasattr(r, 'value') else r for r in roles}

    def decorador(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            rol_actual = session.get("rol")

            # 1. Si no hay rol en la sesión, no está autenticado
            if not rol_actual:
                return jsonify({
                    "error": "No autenticado.",
                    "mensaje": "Debes iniciar sesión para acceder a este recurso."
                }), 401

            # 2. Si tiene sesión pero su rol no está autorizado
            if rol_actual not in valores:
                return jsonify({
                    "error": "Acceso denegado.",
                    "mensaje": "No tienes los permisos necesarios para realizar esta acción."
                }), 403

            return view(*args, **kwargs)

        return wrapped

    return decorador


def turno_required(view):
    """Verifica que exista un turno de caja abierto asociado a la sesión.

    Si el turno es válido, lo asigna a g.turno. De lo contrario, retorna 401: para la
    terminal equivale a una sesión inválida (el cliente regresa al login).
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        turno_id = session.get("turno_id")
        turno = None

        if turno_id:
            with db_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.id, t.tienda_id, t.usuario_id, t.fondo_inicial,
                           ti.nombre AS tienda_nombre, u.nombre AS usuario_nombre
                    FROM turnos_caja t
                    JOIN tiendas ti ON ti.id = t.tienda_id
                    JOIN usuarios u ON u.id = t.usuario_id
                    WHERE t.id = %s AND t.estado = 'abierto'
                    """,
                    (turno_id,),
                )
                turno = cursor.fetchone()

        if not turno:
            # Limpiamos el turno inválido de la sesión
            session.pop("turno_id", None)
            return jsonify({
                "error": "Caja cerrada.",
                "mensaje": "No hay una caja abierta para esta sesión. Pide a un supervisor o admin que la abra."
            }), 401

        g.turno = turno
        return view(*args, **kwargs)

    return wrapped