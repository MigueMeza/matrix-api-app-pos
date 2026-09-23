import json
import pymysql
from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import db_cursor
from ..permisos import Rol

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
def _solo_super_admin():
    if request.endpoint == "admin.login":
        return None
    if session.get("rol") != Rol.SUPER_ADMIN.value:
        return jsonify(error="Acceso no autorizado."), 403


@admin_bp.route("/login", methods=["POST"])
def login():
    datos = request.get_json(silent=True) or {}
    usuario_login = (datos.get("usuario_login") or "").strip()
    password = datos.get("password") or ""

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nombre, rol, password_hash
            FROM usuarios
            WHERE usuario_login = %s AND rol = %s AND activo = 1
            """,
            (usuario_login, Rol.SUPER_ADMIN.value),
        )
        usuario = cursor.fetchone()

    if not usuario or not usuario["password_hash"] or not check_password_hash(usuario["password_hash"], password):
        return jsonify(error="Usuario o contraseña incorrectos."), 401

    session.clear()
    session["usuario_id"] = usuario["id"]
    session["nombre"] = usuario["nombre"]
    session["rol"] = usuario["rol"]
    session["contexto"] = "admin"

    return jsonify(
        mensaje="Login de administrador exitoso.",
        usuario_id=usuario["id"],
        usuario={"id": usuario["id"], "nombre": usuario["nombre"], "rol": usuario["rol"]},
    ), 200


def _tiendas_activas(cursor):
    cursor.execute("SELECT id, nombre FROM tiendas WHERE activo = 1 ORDER BY nombre")
    return cursor.fetchall()


@admin_bp.route("/inventarios/<int:id>", methods=["DELETE"])
def inventario_eliminar(id):
    with db_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM inventarios WHERE id = %s", (id,))

    return jsonify(mensaje="Inventario eliminado."), 200


@admin_bp.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    if request.method == "GET":
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.nombre, u.usuario_login, u.rol, u.activo, t.nombre AS tienda_nombre
                FROM usuarios u
                JOIN tiendas t ON t.id = u.tienda_id
                ORDER BY FIELD(u.rol, 'super_admin', 'supervisor', 'vendedor'), u.nombre
                """
            )
            usuarios = cursor.fetchall()
            tiendas = _tiendas_activas(cursor)

        return jsonify(usuarios=usuarios, tiendas=tiendas, roles=[r.value for r in Rol]), 200

    # POST (Crear usuario)
    datos = request.get_json(silent=True) or {}
    tienda_id = datos.get("tienda_id")
    nombre = (datos.get("nombre") or "").strip()
    usuario_login = (datos.get("usuario_login") or "").strip()
    rol = datos.get("rol")
    password = datos.get("password") or ""

    roles_validos = {r.value for r in Rol}
    if not tienda_id or not nombre or not usuario_login or rol not in roles_validos:
        return jsonify(error="Completa todos los campos con valores válidos."), 400

    if rol != Rol.VENDEDOR.value and not password:
        return jsonify(error="Los roles supervisor y super-admin necesitan contraseña."), 400

    password_hash = generate_password_hash(password) if password else None
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO usuarios (tienda_id, nombre, usuario_login, password_hash, rol)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (tienda_id, nombre, usuario_login, password_hash, rol),
            )
    except pymysql.err.IntegrityError:
        return jsonify(error="Ese usuario ya existe (usuario_login duplicado)."), 409

    return jsonify(mensaje="Usuario creado exitosamente."), 201


@admin_bp.route("/usuarios/<int:usuario_id>/toggle", methods=["POST"])
def usuarios_toggle(usuario_id):
    with db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE usuarios SET activo = NOT activo WHERE id = %s", (usuario_id,))
    return jsonify(mensaje="Estado del usuario actualizado."), 200


@admin_bp.route("/tiendas", methods=["GET", "POST"])
def tiendas():
    if request.method == "GET":
        with db_cursor() as cursor:
            cursor.execute("SELECT id, nombre, direccion, activo FROM tiendas ORDER BY nombre")
            tiendas = cursor.fetchall()
        return jsonify(tiendas=tiendas), 200

    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    direccion = (datos.get("direccion") or "").strip() or None

    if not nombre:
        return jsonify(error="El nombre es obligatorio."), 400

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO tiendas (nombre, direccion) VALUES (%s, %s)",
            (nombre, direccion),
        )

    return jsonify(mensaje="Tienda creada exitosamente."), 201


@admin_bp.route("/tiendas/<int:tienda_id>/toggle", methods=["POST"])
def tiendas_toggle(tienda_id):
    with db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE tiendas SET activo = NOT activo WHERE id = %s", (tienda_id,))
    return jsonify(mensaje="Estado de la tienda actualizado."), 200


@admin_bp.route("/pedidos", methods=["GET"])
def pedidos_listar():
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.fecha_pedido, p.fecha_disponible, p.estado, p.observaciones,
                   c.nombre AS cliente_nombre, t.nombre AS tienda_nombre
            FROM pedidos p
            JOIN clientes c ON c.id = p.cliente_id
            JOIN tiendas t ON t.id = p.tienda_id
            ORDER BY FIELD(p.estado, 'pendiente', 'disponible', 'entregado', 'cancelado'), p.fecha_pedido DESC
            """
        )
        pedidos = cursor.fetchall()

    return jsonify(pedidos=pedidos), 200


@admin_bp.route("/pedidos/<int:pedido_id>/detalles", methods=["GET"])
def pedidos_detalles(pedido_id):
    """Líneas del pedido, para asignar las que vienen fuera de catálogo."""
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT pd.id AS detalle_id, pd.producto_id, pd.descripcion, pd.talla, pd.cantidad, pd.comentario,
                   pr.nombre AS producto_nombre, pr.talla AS producto_talla, pr.color AS producto_color,
                   pr.precio AS producto_precio
            FROM pedido_detalles pd
            LEFT JOIN productos pr ON pr.id = pd.producto_id
            WHERE pd.pedido_id = %s
            ORDER BY pd.id
            """,
            (pedido_id,),
        )
        detalles = cursor.fetchall()
    return jsonify(detalles=detalles), 200


@admin_bp.route("/pedidos/<int:pedido_id>/detalles/<int:detalle_id>", methods=["PUT"])
def pedidos_asignar_producto(pedido_id, detalle_id):
    """Asigna un producto real del catálogo (con precio) a una línea fuera de catálogo.

    Se hace cuando llega la mercancía; si el producto no existe, primero se da de alta en /admin/productos.
    """
    datos = request.get_json(silent=True) or {}
    try:
        producto_id = int(datos.get("producto_id"))
    except (TypeError, ValueError):
        return jsonify(error="Indica el producto del catálogo."), 400

    with db_cursor(commit=True) as cursor:
        cursor.execute("SELECT id FROM productos WHERE id = %s AND activo = 1", (producto_id,))
        if not cursor.fetchone():
            return jsonify(error="El producto no existe o está descontinuado."), 400

        cursor.execute(
            """
            UPDATE pedido_detalles pd
            JOIN pedidos p ON p.id = pd.pedido_id
            SET pd.producto_id = %s
            WHERE pd.id = %s AND pd.pedido_id = %s AND p.estado = 'pendiente'
            """,
            (producto_id, detalle_id, pedido_id),
        )
        if cursor.rowcount == 0:
            return jsonify(error="La línea no existe o el pedido ya no está pendiente."), 400

    return jsonify(mensaje="Producto asignado."), 200


@admin_bp.route("/pedidos/<int:pedido_id>/disponible", methods=["POST"])
def pedidos_disponible(pedido_id):
    """La mercancía llegó. NO se suma al inventario: ya es del cliente y queda reservada para el pedido.

    Si se sumara, cualquier venta normal podría llevársela antes de que el cliente pase por ella.
    Todas las líneas deben tener un producto del catálogo: sin él no hay precio para cobrarlo.
    """
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT descripcion, talla FROM pedido_detalles WHERE pedido_id = %s AND producto_id IS NULL",
            (pedido_id,),
        )
        sin_asignar = [f"{d['descripcion']} ({d['talla']})" if d["talla"] else d["descripcion"] for d in cursor.fetchall()]
        if sin_asignar:
            return jsonify(
                error="Asigna un producto del catálogo a: " + ", ".join(sin_asignar) + ".",
                sin_asignar=sin_asignar,
            ), 400

        cursor.execute(
            "UPDATE pedidos SET estado = 'disponible', fecha_disponible = NOW() WHERE id = %s AND estado = 'pendiente'",
            (pedido_id,),
        )
        if cursor.rowcount == 0:
            return jsonify(error="Este pedido no existe o ya no está pendiente."), 400

    return jsonify(mensaje="Pedido marcado como disponible."), 200


@admin_bp.route("/pedidos/<int:pedido_id>/cancelar", methods=["POST"])
def pedidos_cancelar(pedido_id):
    """Si el pedido ya estaba disponible, la mercancía reservada pasa al inventario de la tienda para venderse."""
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT tienda_id, estado FROM pedidos WHERE id = %s AND estado IN ('pendiente', 'disponible') FOR UPDATE",
            (pedido_id,),
        )
        pedido = cursor.fetchone()
        if not pedido:
            return jsonify(error="Este pedido no existe o ya no se puede cancelar."), 400

        if pedido["estado"] == "disponible":
            cursor.execute(
                "SELECT producto_id, cantidad FROM pedido_detalles WHERE pedido_id = %s AND producto_id IS NOT NULL",
                (pedido_id,),
            )
            for detalle in cursor.fetchall():
                cursor.execute(
                    """
                    INSERT INTO inventarios (tienda_id, producto_id, cantidad)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE cantidad = cantidad + VALUES(cantidad)
                    """,
                    (pedido["tienda_id"], detalle["producto_id"], detalle["cantidad"]),
                )

        cursor.execute("UPDATE pedidos SET estado = 'cancelado' WHERE id = %s", (pedido_id,))

    mensaje = "Pedido cancelado."
    if pedido["estado"] == "disponible":
        mensaje += " La mercancía se agregó al inventario de la tienda."
    return jsonify(mensaje=mensaje), 200


@admin_bp.route("/apartados", methods=["GET"])
def apartados_listar():
    with db_cursor() as cursor:
        cursor.execute("SELECT * FROM v_apartados_resumen ORDER BY fecha_creacion DESC")
        apartados = cursor.fetchall()

    for item in apartados:
        if "total" in item:
            item["total"] = float(item["total"])

    return jsonify(apartados=apartados), 200

@admin_bp.route("/apartados/<int:apartado_id>/devolver_inventario", methods=["POST"])
def apartados_devolver_inventario(apartado_id):
    """Regresa al inventario de su tienda las piezas de un apartado que no se va a entregar.

    Caso normal: el apartado expiró (más de 3 meses) y el cliente no terminó de pagar. También sirve si el
    cliente desiste antes. Queda 'vencido' si ya había expirado, o 'cancelado' si no. Los abonos NO se
    tocan: siguen registrados (qué hacer con ese dinero es decisión del negocio, fuera del sistema).
    """
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            SELECT tienda_id,
                   NOW() > DATE_ADD(fecha_creacion, INTERVAL 3 MONTH) AS expirado
            FROM apartados
            WHERE id = %s AND estado IN ('activo', 'liquidado')
            FOR UPDATE
            """,
            (apartado_id,),
        )
        apartado = cursor.fetchone()
        if not apartado:
            return jsonify(error="El apartado no existe o ya fue entregado, cancelado o devuelto."), 400

        cursor.execute(
            "SELECT producto_id, cantidad FROM apartado_detalles WHERE apartado_id = %s",
            (apartado_id,),
        )
        for detalle in cursor.fetchall():
            cursor.execute(
                """
                INSERT INTO inventarios (tienda_id, producto_id, cantidad)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE cantidad = cantidad + VALUES(cantidad)
                """,
                (apartado["tienda_id"], detalle["producto_id"], detalle["cantidad"]),
            )

        estado = "vencido" if apartado["expirado"] else "cancelado"
        cursor.execute("UPDATE apartados SET estado = %s WHERE id = %s", (estado, apartado_id))

    return jsonify(
        mensaje="La mercancía del apartado regresó al inventario de la tienda.",
        estado=estado,
    ), 200


# Resumen de inicio, ingreso de mercancía y consulta de ventas: viven en su propio módulo pero registran sus rutas en admin_bp.
# Se importa al final porque necesita admin_bp ya definido.
from . import admin_inventario, admin_resumen, admin_ventas  # noqa: E402,F401
