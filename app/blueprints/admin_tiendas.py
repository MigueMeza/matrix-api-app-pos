"""Tiendas para /admin: alta, edición, deshabilitar/habilitar y eliminar.

Las rutas se registran en admin_bp, así que heredan su before_request (solo super_admin).
Al deshabilitar o eliminar, los productos de la tienda se pueden mandar a otra (todos a una misma tienda;
después se reparten con "Cambiar de tienda" en Inventarios). Una tienda con historial (ventas, cajas,
pedidos, apartados) no se puede eliminar: se deshabilita.
"""
from flask import jsonify, request

from ..db import db_cursor
from .admin import admin_bp

SQL_HISTORIAL_TIENDA = """
    EXISTS (SELECT 1 FROM ventas WHERE tienda_id = t.id)
    OR EXISTS (SELECT 1 FROM turnos_caja WHERE tienda_id = t.id)
    OR EXISTS (SELECT 1 FROM apartados WHERE tienda_id = t.id)
    OR EXISTS (SELECT 1 FROM pedidos WHERE tienda_id = t.id)
"""

SQL_DATOS_TIENDA = f"""
    SELECT t.id, t.nombre, t.direccion, t.activo,
           (SELECT COUNT(*) FROM inventarios i WHERE i.tienda_id = t.id AND i.cantidad > 0) AS productos,
           (SELECT COALESCE(SUM(i.cantidad), 0) FROM inventarios i WHERE i.tienda_id = t.id) AS piezas,
           (SELECT COUNT(*) FROM usuarios u WHERE u.tienda_id = t.id AND u.activo = 1) AS empleados,
           (SELECT COUNT(*) FROM usuarios u WHERE u.tienda_id = t.id) AS empleados_total,
           ({SQL_HISTORIAL_TIENDA}) AS tiene_historial,
           EXISTS (SELECT 1 FROM turnos_caja c WHERE c.tienda_id = t.id AND c.estado = 'abierto') AS caja_abierta
    FROM tiendas t
"""


class TiendaInvalida(Exception):
    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


def _normalizar(t):
    for campo in ("activo", "tiene_historial", "caja_abierta"):
        t[campo] = bool(t[campo])
    for campo in ("productos", "piezas", "empleados", "empleados_total"):
        t[campo] = int(t[campo])
    return t


def _tienda(cursor, tienda_id):
    cursor.execute(SQL_DATOS_TIENDA + " WHERE t.id = %s FOR UPDATE", (tienda_id,))
    tienda = cursor.fetchone()
    if not tienda:
        raise TiendaInvalida("La tienda no existe.", 404)
    return _normalizar(tienda)


def _datos(cursor, datos, tienda_id=None):
    """(nombre, dirección) validados; el nombre no se puede repetir."""
    nombre = " ".join((datos.get("nombre") or "").split())[:150]
    direccion = " ".join((datos.get("direccion") or "").split())[:255] or None
    if not nombre:
        raise TiendaInvalida("El nombre de la tienda es obligatorio.")
    cursor.execute("SELECT id FROM tiendas WHERE LOWER(nombre) = LOWER(%s) AND id <> %s", (nombre, tienda_id or 0))
    if cursor.fetchone():
        raise TiendaInvalida(f"Ya existe una tienda llamada {nombre}.", 409)
    return nombre, direccion


def _destino(cursor, tienda, destino_id):
    """Tienda activa, distinta de la que se da de baja, a la que se mandan productos (y empleados al eliminar)."""
    try:
        destino_id = int(destino_id)
    except (TypeError, ValueError):
        raise TiendaInvalida("Elige la tienda a la que se mandan los productos.")
    if destino_id == tienda["id"]:
        raise TiendaInvalida("La tienda destino debe ser otra.")
    cursor.execute("SELECT id, nombre FROM tiendas WHERE id = %s AND activo = 1", (destino_id,))
    destino = cursor.fetchone()
    if not destino:
        raise TiendaInvalida("La tienda destino no existe o está inactiva.")
    return destino


def _no_es_la_ultima_activa(cursor, tienda):
    if not tienda["activo"]:
        return
    cursor.execute("SELECT COUNT(*) AS n FROM tiendas WHERE activo = 1")
    if cursor.fetchone()["n"] <= 1:
        raise TiendaInvalida("Es la única tienda activa: debe quedar al menos una.")


def _mover_productos(cursor, origen_id, destino_id):
    """Todas las piezas de origen se suman a destino; origen queda sin renglones de inventario."""
    # El origen va en una subconsulta con alias: leer y escribir la misma tabla sin alias hace que
    # "cantidad" sea ambigua en el ON DUPLICATE KEY UPDATE (error 1052 de MySQL)
    cursor.execute(
        """
        INSERT INTO inventarios (tienda_id, producto_id, cantidad)
        SELECT origen.tienda_destino, origen.producto_id, origen.piezas
        FROM (
            SELECT %s AS tienda_destino, producto_id, cantidad AS piezas
            FROM inventarios WHERE tienda_id = %s AND cantidad > 0
        ) AS origen
        ON DUPLICATE KEY UPDATE cantidad = inventarios.cantidad + origen.piezas
        """,
        (destino_id, origen_id),
    )
    cursor.execute("DELETE FROM inventarios WHERE tienda_id = %s", (origen_id,))


@admin_bp.route("/tiendas", methods=["GET"])
def tiendas_listar():
    with db_cursor() as cursor:
        cursor.execute(SQL_DATOS_TIENDA + " ORDER BY t.activo DESC, t.nombre")
        tiendas = [_normalizar(t) for t in cursor.fetchall()]
    return jsonify(tiendas=tiendas), 200


@admin_bp.route("/tiendas", methods=["POST"])
def tiendas_crear():
    try:
        with db_cursor(commit=True) as cursor:
            nombre, direccion = _datos(cursor, request.get_json(silent=True) or {})
            cursor.execute("INSERT INTO tiendas (nombre, direccion) VALUES (%s, %s)", (nombre, direccion))
            tienda_id = cursor.lastrowid
    except TiendaInvalida as e:
        return jsonify(error=e.mensaje), e.status
    return jsonify(mensaje="Tienda registrada.", tienda_id=tienda_id), 201


@admin_bp.route("/tiendas/<int:tienda_id>", methods=["PUT"])
def tiendas_editar(tienda_id):
    try:
        with db_cursor(commit=True) as cursor:
            _tienda(cursor, tienda_id)
            nombre, direccion = _datos(cursor, request.get_json(silent=True) or {}, tienda_id)
            cursor.execute("UPDATE tiendas SET nombre = %s, direccion = %s WHERE id = %s", (nombre, direccion, tienda_id))
    except TiendaInvalida as e:
        return jsonify(error=e.mensaje), e.status
    return jsonify(mensaje="Tienda actualizada."), 200


@admin_bp.route("/tiendas/<int:tienda_id>/estado", methods=["POST"])
def tiendas_estado(tienda_id):
    """Deshabilitar (opcionalmente mandando sus productos a otra tienda) o volver a habilitar.

    Una tienda deshabilitada no aparece para abrir caja, vender ni ingresar mercancía; su historial se conserva.
    """
    datos = request.get_json(silent=True) or {}
    activo = bool(datos.get("activo"))
    try:
        with db_cursor(commit=True) as cursor:
            tienda = _tienda(cursor, tienda_id)
            mensaje = "Tienda habilitada."
            if not activo:
                _no_es_la_ultima_activa(cursor, tienda)
                if tienda["caja_abierta"]:
                    raise TiendaInvalida("Tiene una caja abierta: primero hay que hacerle el corte.", 409)
                mensaje = "Tienda deshabilitada."
                if datos.get("tienda_destino_id"):
                    destino = _destino(cursor, tienda, datos["tienda_destino_id"])
                    _mover_productos(cursor, tienda_id, destino["id"])
                    mensaje += f" Sus {tienda['piezas']} pieza(s) se mandaron a {destino['nombre']}."
            cursor.execute("UPDATE tiendas SET activo = %s WHERE id = %s", (activo, tienda_id))
    except TiendaInvalida as e:
        return jsonify(error=e.mensaje), e.status
    return jsonify(mensaje=mensaje), 200


@admin_bp.route("/tiendas/<int:tienda_id>", methods=["DELETE"])
def tiendas_eliminar(tienda_id):
    """Solo sin historial. Si tiene productos o empleados, se mandan a `tienda_destino_id` (obligatorio en ese caso)."""
    try:
        with db_cursor(commit=True) as cursor:
            tienda = _tienda(cursor, tienda_id)
            _no_es_la_ultima_activa(cursor, tienda)
            if tienda["tiene_historial"]:
                raise TiendaInvalida(
                    "Tiene ventas, cajas, pedidos o apartados registrados: no se puede eliminar sin perder ese "
                    "historial. Deshabilítala en su lugar.", 409)

            destino = None
            if tienda["piezas"] > 0 or tienda["empleados_total"] > 0:
                destino = _destino(cursor, tienda, request.args.get("tienda_destino_id"))
                _mover_productos(cursor, tienda_id, destino["id"])
                cursor.execute("UPDATE usuarios SET tienda_id = %s WHERE tienda_id = %s", (destino["id"], tienda_id))
            cursor.execute("DELETE FROM inventarios WHERE tienda_id = %s", (tienda_id,))
            cursor.execute("DELETE FROM tiendas WHERE id = %s", (tienda_id,))
    except TiendaInvalida as e:
        return jsonify(error=e.mensaje), e.status

    mensaje = "Tienda eliminada."
    if destino:
        mensaje += f" Sus productos y empleados pasaron a {destino['nombre']}."
    return jsonify(mensaje=mensaje), 200
