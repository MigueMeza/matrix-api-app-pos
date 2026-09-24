from flask import Blueprint, jsonify, request

from ..auth import turno_required
from ..db import db_cursor

clientes_bp = Blueprint("clientes", __name__)


class ClienteInvalido(Exception):
    """El cliente elegido no existe o faltan datos para registrar uno nuevo."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def resolver_cliente(cursor, cliente_id, nombre, telefono):
    """Devuelve el id del cliente: el elegido (si existe y está activo) o uno nuevo con nombre/teléfono.

    Lo usan pedidos y apartados, donde el cajero elige un cliente registrado o captura uno nuevo.
    Lanza ClienteInvalido si no se puede.
    """
    nombre = (nombre or "").strip()
    telefono = (telefono or "").strip() or None

    if cliente_id:
        try:
            cliente_id = int(cliente_id)
        except (TypeError, ValueError):
            raise ClienteInvalido("El cliente seleccionado no existe.")
        cursor.execute("SELECT id FROM clientes WHERE id = %s AND activo = 1", (cliente_id,))
        if not cursor.fetchone():
            raise ClienteInvalido("El cliente seleccionado no existe.")
        return cliente_id

    if not nombre:
        raise ClienteInvalido("Selecciona un cliente existente o captura uno nuevo.")

    cursor.execute(
        "INSERT INTO clientes (nombre, telefono) VALUES (%s, %s)",
        (nombre[:150], telefono[:30] if telefono else None),
    )
    return cursor.lastrowid


@clientes_bp.route("/clientes", methods=["GET"])
@turno_required
def buscar():
    """Busca clientes activos por nombre o teléfono (para elegirlos al registrar un pedido o apartado)."""
    buscar = request.args.get("buscar", "").strip()

    if len(buscar) < 2:
        return jsonify(resultados=[]), 200

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nombre, telefono
            FROM clientes
            WHERE activo = 1 AND (nombre LIKE %s OR telefono LIKE %s)
            ORDER BY nombre
            LIMIT 20
            """,
            (f"%{buscar}%", f"%{buscar}%"),
        )
        clientes = cursor.fetchall()

    return jsonify(resultados=clientes), 200
