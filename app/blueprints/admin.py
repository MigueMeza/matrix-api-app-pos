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

    return jsonify(mensaje="Login de administrador exitoso.", usuario_id=usuario["id"]), 200


def _tiendas_activas(cursor):
    cursor.execute("SELECT id, nombre FROM tiendas WHERE activo = 1 ORDER BY nombre")
    return cursor.fetchall()


@admin_bp.route("/", methods=["GET"])
def dashboard():
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM tiendas WHERE activo = 1")
        tiendas_activas = cursor.fetchone()["n"]

        cursor.execute("SELECT COUNT(*) AS n FROM productos WHERE activo = 1")
        productos_activos = cursor.fetchone()["n"]

        cursor.execute("SELECT COUNT(*) AS n FROM usuarios WHERE rol = %s AND activo = 1", (Rol.VENDEDOR.value,))
        vendedores_activos = cursor.fetchone()["n"]

        cursor.execute(
            """
            SELECT COALESCE(SUM(i.cantidad * p.precio), 0) AS valor
            FROM inventarios i JOIN productos p ON p.id = i.producto_id
            """
        )
        valor_inventario = float(cursor.fetchone()["valor"])

        cursor.execute("SELECT COUNT(*) AS n FROM turnos_caja WHERE estado = 'abierto'")
        turnos_abiertos = cursor.fetchone()["n"]

        cursor.execute("SELECT COUNT(*) AS n FROM pedidos WHERE estado = 'pendiente'")
        pedidos_pendientes = cursor.fetchone()["n"]

    return jsonify(
        tiendas_activas=tiendas_activas,
        productos_activos=productos_activos,
        vendedores_activos=vendedores_activos,
        valor_inventario=valor_inventario,
        turnos_abiertos=turnos_abiertos,
        pedidos_pendientes=pedidos_pendientes,
    ), 200


@admin_bp.route("/productos", methods=["GET"])
def productos_listar():
    tienda_id = request.args.get("tienda_id", type=int, default=0)
    buscar = request.args.get("buscar", "").strip()

    with db_cursor() as cursor:
        tiendas = _tiendas_activas(cursor)

        sql = """
            SELECT p.id AS producto_id, i.id AS inventario_id, p.nombre, p.talla, p.color,
                   p.precio, i.cantidad, t.nombre AS tienda
            FROM inventarios i
            JOIN productos p ON p.id = i.producto_id
            JOIN tiendas t ON t.id = i.tienda_id
            WHERE 1=1
        """
        parametros = []
        if tienda_id != 0:
            sql += " AND i.tienda_id = %s"
            parametros.append(tienda_id)
        if buscar:
            sql += " AND p.nombre LIKE %s"
            parametros.append(f"%{buscar}%")
        sql += " ORDER BY p.nombre"

        cursor.execute(sql, parametros)
        inventario = cursor.fetchall()

    for item in inventario:
        item["precio"] = float(item["precio"])

    return jsonify(tiendas=tiendas, tienda_id_seleccionada=tienda_id, inventario=inventario), 200


@admin_bp.route("/productos/buscar_por_codigo", methods=["GET"])
def productos_buscar_por_codigo():
    codigo_barras = request.args.get("codigo_barras", "").strip()

    if not codigo_barras:
        return jsonify(encontrado=False), 200

    with db_cursor() as cursor:
        cursor.execute(
            "SELECT nombre, talla, color, precio FROM productos WHERE codigo_barras = %s",
            (codigo_barras,),
        )
        producto = cursor.fetchone()

    if not producto:
        return jsonify(encontrado=False), 200

    return jsonify(
        encontrado=True,
        nombre=producto["nombre"],
        talla=producto["talla"],
        color=producto["color"],
        precio=float(producto["precio"]),
    ), 200


@admin_bp.route("/productos/ingreso/lote", methods=["POST"])
def productos_ingreso_guardar_lote():
    datos = request.get_json(silent=True) or {}
    items = datos.get("items", [])

    if not items:
        return jsonify(error="No se enviaron ítems para procesar."), 400

    with db_cursor(commit=True) as cursor:
        for item in items:
            codigo_barras = (item.get("codigo_barras") or "").strip()
            tienda_id = int(item.get("tienda_id"))
            cantidad = int(item.get("cantidad"))

            cursor.execute("SELECT id FROM productos WHERE codigo_barras = %s", (codigo_barras,))
            producto = cursor.fetchone()

            if producto:
                producto_id = producto["id"]
            else:
                nombre = (item.get("nombre") or "").strip()
                talla = (item.get("talla") or "").strip() or None
                color = (item.get("color") or "").strip() or None
                precio = float(item.get("precio"))
                cursor.execute(
                    """
                    INSERT INTO productos (nombre, talla, color, precio, codigo_barras)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (nombre, talla, color, precio, codigo_barras),
                )
                producto_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO inventarios (tienda_id, producto_id, cantidad)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE cantidad = cantidad + VALUES(cantidad)
                """,
                (tienda_id, producto_id, cantidad),
            )

    return jsonify(mensaje="Lote de productos procesado exitosamente."), 200


@admin_bp.route("/inventarios/<int:id>", methods=["PUT"])
def inventario_editar(id):
    datos = request.get_json(silent=True) or {}
    cantidad = datos.get("cantidad")

    if cantidad is None:
        return jsonify(error="Debes proporcionar la nueva cantidad."), 400

    with db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE inventarios SET cantidad = %s WHERE id = %s", (cantidad, id))

    return jsonify(mensaje="Inventario actualizado."), 200


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


@admin_bp.route("/pedidos/<int:pedido_id>/disponible", methods=["POST"])
def pedidos_disponible(pedido_id):
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT tienda_id FROM pedidos WHERE id = %s AND estado = 'pendiente' FOR UPDATE",
            (pedido_id,),
        )
        pedido = cursor.fetchone()
        if not pedido:
            return jsonify(error="Este pedido no existe o ya no está pendiente."), 400

        cursor.execute(
            "SELECT producto_id, cantidad FROM pedido_detalles WHERE pedido_id = %s",
            (pedido_id,),
        )
        detalles = cursor.fetchall()

        for detalle in detalles:
            cursor.execute(
                """
                INSERT INTO inventarios (tienda_id, producto_id, cantidad)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE cantidad = cantidad + VALUES(cantidad)
                """,
                (pedido["tienda_id"], detalle["producto_id"], detalle["cantidad"]),
            )

        cursor.execute(
            "UPDATE pedidos SET estado = 'disponible', fecha_disponible = NOW() WHERE id = %s",
            (pedido_id,),
        )

    return jsonify(mensaje="Pedido marcado como disponible e inventario acreditado."), 200


@admin_bp.route("/pedidos/<int:pedido_id>/cancelar", methods=["POST"])
def pedidos_cancelar(pedido_id):
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE pedidos SET estado = 'cancelado' WHERE id = %s AND estado IN ('pendiente', 'disponible')",
            (pedido_id,),
        )
    return jsonify(mensaje="Pedido cancelado."), 200


@admin_bp.route("/apartados", methods=["GET"])
def apartados_listar():
    with db_cursor() as cursor:
        cursor.execute("SELECT * FROM v_apartados_resumen ORDER BY fecha_creacion DESC")
        apartados = cursor.fetchall()

    for item in apartados:
        if "total" in item:
            item["total"] = float(item["total"])

    return jsonify(apartados=apartados), 200