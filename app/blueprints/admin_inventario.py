"""Alta de productos, ingreso de mercancía y corrección de inventarios por tienda, para /admin.

Las rutas se registran en admin_bp, así que heredan su before_request (solo super_admin).
Precios de un producto: precio (venta), precio_compra (costo para la tienda) y precio_publico_proveedor
(opcional). El precio sugerido que ve el admin es precio_compra + configuracion.margen_precio_sugerido.
"""
from flask import jsonify, request

from ..db import db_cursor
from .admin import admin_bp

CLAVE_MARGEN = "margen_precio_sugerido"


class IngresoInvalido(Exception):
    """Un renglón del ingreso no es válido: no se guarda nada del lote."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def _margen(cursor):
    cursor.execute("SELECT valor FROM configuracion WHERE clave = %s", (CLAVE_MARGEN,))
    fila = cursor.fetchone()
    return float(fila["valor"]) if fila else 120.0


def _monto(valor, campo, requerido=True):
    """Monto >= 0 con 2 decimales; None si es opcional y no viene."""
    if valor in (None, ""):
        if requerido:
            raise IngresoInvalido(f"Falta el {campo}.")
        return None
    try:
        monto = round(float(valor), 2)
    except (TypeError, ValueError):
        raise IngresoInvalido(f"El {campo} no es válido.")
    if monto < 0:
        raise IngresoInvalido(f"El {campo} no puede ser negativo.")
    return monto


def _precios(producto):
    for campo in ("precio", "precio_compra", "precio_publico_proveedor"):
        if producto.get(campo) is not None:
            producto[campo] = float(producto[campo])
    return producto


@admin_bp.route("/ingreso/opciones", methods=["GET"])
def ingreso_opciones():
    """Tiendas activas (a las que se puede ingresar mercancía) y el margen del precio sugerido."""
    with db_cursor() as cursor:
        cursor.execute("SELECT id, nombre FROM tiendas WHERE activo = 1 ORDER BY nombre")
        tiendas = cursor.fetchall()
        margen = _margen(cursor)
    return jsonify(tiendas=tiendas, margen_precio_sugerido=margen), 200


@admin_bp.route("/configuracion/margen", methods=["PUT"])
def configuracion_margen():
    """Cambia el monto que se suma al precio de compra para sugerir el precio de venta (aplica en adelante)."""
    datos = request.get_json(silent=True) or {}
    try:
        margen = _monto(datos.get("margen_precio_sugerido"), "margen")
    except IngresoInvalido as e:
        return jsonify(error=e.mensaje), 400

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO configuracion (clave, valor) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE valor = VALUES(valor)
            """,
            (CLAVE_MARGEN, f"{margen:.2f}"),
        )
    return jsonify(mensaje="Margen actualizado.", margen_precio_sugerido=margen), 200


@admin_bp.route("/productos/buscar_por_codigo", methods=["GET"])
def productos_buscar_por_codigo():
    """Producto del catálogo con ese código (y en qué tiendas hay existencias), para el ingreso de mercancía."""
    codigo_barras = request.args.get("codigo_barras", "").strip()
    if not codigo_barras:
        return jsonify(encontrado=False), 200

    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nombre, talla, color, precio, precio_compra, precio_publico_proveedor, activo
            FROM productos
            WHERE codigo_barras = %s
            """,
            (codigo_barras,),
        )
        producto = cursor.fetchone()
        if not producto:
            return jsonify(encontrado=False), 200

        cursor.execute(
            """
            SELECT t.nombre AS tienda, i.cantidad
            FROM inventarios i JOIN tiendas t ON t.id = i.tienda_id
            WHERE i.producto_id = %s
            ORDER BY t.nombre
            """,
            (producto["id"],),
        )
        existencias = cursor.fetchall()

    producto["activo"] = bool(producto["activo"])
    return jsonify(encontrado=True, producto=_precios(producto), existencias=existencias), 200


@admin_bp.route("/productos/ingreso/lote", methods=["POST"])
def productos_ingreso_guardar_lote():
    """Registra un ingreso de mercancía: da de alta los productos nuevos y suma las piezas a cada tienda.

    items: [{codigo_barras?, nombre, talla?, color?, tienda_id, cantidad,
             precio (venta), precio_compra, precio_publico_proveedor?}]
    - Producto nuevo (código que no existe, o sin código): se crea con esos datos y precios.
    - Producto existente (mismo código): se suman las piezas y se actualizan sus precios.
    Todo el lote se guarda junto: si un renglón está mal, no se guarda nada.
    """
    items = (request.get_json(silent=True) or {}).get("items", [])
    if not items:
        return jsonify(error="El ingreso no tiene productos."), 400

    nuevos, actualizados, piezas = set(), set(), 0
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute("SELECT id FROM tiendas WHERE activo = 1")
            tiendas_activas = {t["id"] for t in cursor.fetchall()}

            for numero, item in enumerate(items, start=1):
                try:
                    tienda_id = int(item.get("tienda_id"))
                    cantidad = int(item.get("cantidad"))
                except (TypeError, ValueError):
                    raise IngresoInvalido(f"Renglón {numero}: la tienda o la cantidad no son válidas.")
                if tienda_id not in tiendas_activas:
                    raise IngresoInvalido(f"Renglón {numero}: la tienda no existe o está inactiva.")
                if cantidad <= 0:
                    raise IngresoInvalido(f"Renglón {numero}: la cantidad debe ser mayor a 0.")

                try:
                    precio = _monto(item.get("precio"), "precio de venta")
                    precio_compra = _monto(item.get("precio_compra"), "precio de compra")
                    precio_proveedor = _monto(item.get("precio_publico_proveedor"), "precio al público del proveedor",
                                              requerido=False)
                except IngresoInvalido as e:
                    raise IngresoInvalido(f"Renglón {numero}: {e.mensaje}")
                if precio <= 0:
                    raise IngresoInvalido(f"Renglón {numero}: el precio de venta debe ser mayor a 0.")

                codigo_barras = (item.get("codigo_barras") or "").strip() or None
                producto = None
                if codigo_barras:
                    cursor.execute(
                        "SELECT id, nombre, activo FROM productos WHERE codigo_barras = %s FOR UPDATE",
                        (codigo_barras,),
                    )
                    producto = cursor.fetchone()

                if producto:
                    if not producto["activo"]:
                        raise IngresoInvalido(
                            f"Renglón {numero}: {producto['nombre']} ({codigo_barras}) está descontinuado."
                        )
                    producto_id = producto["id"]
                    cursor.execute(
                        """
                        UPDATE productos
                        SET precio = %s, precio_compra = %s,
                            precio_publico_proveedor = COALESCE(%s, precio_publico_proveedor)
                        WHERE id = %s
                        """,
                        (precio, precio_compra, precio_proveedor, producto_id),
                    )
                    if producto_id not in nuevos:
                        actualizados.add(producto_id)
                else:
                    nombre = (item.get("nombre") or "").strip()
                    if not nombre:
                        raise IngresoInvalido(f"Renglón {numero}: falta el nombre del producto nuevo.")
                    cursor.execute(
                        """
                        INSERT INTO productos (nombre, talla, color, precio, precio_compra,
                                               precio_publico_proveedor, codigo_barras)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            nombre[:150],
                            ((item.get("talla") or "").strip() or None),
                            ((item.get("color") or "").strip() or None),
                            precio, precio_compra, precio_proveedor, codigo_barras,
                        ),
                    )
                    producto_id = cursor.lastrowid
                    nuevos.add(producto_id)

                cursor.execute(
                    """
                    INSERT INTO inventarios (tienda_id, producto_id, cantidad)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE cantidad = cantidad + VALUES(cantidad)
                    """,
                    (tienda_id, producto_id, cantidad),
                )
                piezas += cantidad
    except IngresoInvalido as e:
        return jsonify(error=e.mensaje), 400

    return jsonify(
        mensaje="Ingreso registrado.",
        productos_nuevos=len(nuevos),
        productos_actualizados=len(actualizados),
        piezas=piezas,
    ), 200


# ---------------------------------------------------------------------------
# Inventarios: ver y corregir lo que hay en cada tienda
# ---------------------------------------------------------------------------

@admin_bp.route("/inventarios", methods=["GET"])
def inventarios_listar():
    """Existencias por tienda (productos activos, tiendas activas), filtrables por tienda y por nombre o código."""
    tienda_id = request.args.get("tienda_id", type=int, default=0)
    buscar = request.args.get("buscar", "").strip()

    sql = """
        SELECT i.id AS inventario_id, i.cantidad, i.tienda_id, t.nombre AS tienda,
               p.id AS producto_id, p.codigo_barras, p.nombre, p.talla, p.color,
               p.precio, p.precio_compra
        FROM inventarios i
        JOIN productos p ON p.id = i.producto_id
        JOIN tiendas t ON t.id = i.tienda_id
        WHERE p.activo = 1 AND t.activo = 1
    """
    parametros = []
    if tienda_id:
        sql += " AND i.tienda_id = %s"
        parametros.append(tienda_id)
    if buscar:
        sql += " AND (p.nombre LIKE %s OR p.codigo_barras LIKE %s)"
        parametros += [f"%{buscar}%", f"%{buscar}%"]
    sql += " ORDER BY p.nombre, p.talla, p.color, t.nombre"

    with db_cursor() as cursor:
        cursor.execute("SELECT id, nombre FROM tiendas WHERE activo = 1 ORDER BY nombre")
        tiendas = cursor.fetchall()
        cursor.execute(sql, parametros)
        inventario = [_precios(fila) for fila in cursor.fetchall()]

    return jsonify(tiendas=tiendas, inventario=inventario), 200


def _inventario_para_editar(cursor, inventario_id):
    cursor.execute(
        """
        SELECT i.id, i.producto_id, i.tienda_id, i.cantidad, t.nombre AS tienda
        FROM inventarios i JOIN tiendas t ON t.id = i.tienda_id
        WHERE i.id = %s
        FOR UPDATE
        """,
        (inventario_id,),
    )
    fila = cursor.fetchone()
    if not fila:
        raise IngresoInvalido("Ese registro de inventario ya no existe.")
    return fila


@admin_bp.route("/inventarios/<int:inventario_id>", methods=["PUT"])
def inventarios_editar(inventario_id):
    """Corrige un renglón de inventario: la existencia en esa tienda y, si vienen, los datos del producto.

    cantidad: existencia en esta tienda (entero >= 0).
    nombre, codigo_barras, talla, color, precio (venta): son del PRODUCTO, cambian en todas las tiendas.
    Todo se guarda junto o nada.
    """
    datos = request.get_json(silent=True) or {}
    try:
        with db_cursor(commit=True) as cursor:
            inventario = _inventario_para_editar(cursor, inventario_id)

            if "nombre" in datos:
                nombre = (datos.get("nombre") or "").strip()
                if not nombre:
                    raise IngresoInvalido("El nombre del producto no puede quedar vacío.")
                precio = _monto(datos.get("precio"), "precio de venta")
                if precio <= 0:
                    raise IngresoInvalido("El precio de venta debe ser mayor a 0.")
                codigo = (datos.get("codigo_barras") or "").strip() or None
                if codigo:
                    cursor.execute(
                        "SELECT nombre FROM productos WHERE codigo_barras = %s AND id <> %s",
                        (codigo, inventario["producto_id"]),
                    )
                    otro = cursor.fetchone()
                    if otro:
                        raise IngresoInvalido(f"El código {codigo} ya lo tiene otro producto ({otro['nombre']}).")
                cursor.execute(
                    """
                    UPDATE productos
                    SET nombre = %s, codigo_barras = %s, talla = %s, color = %s, precio = %s
                    WHERE id = %s
                    """,
                    (
                        nombre[:150], codigo,
                        ((datos.get("talla") or "").strip() or None),
                        ((datos.get("color") or "").strip() or None),
                        precio, inventario["producto_id"],
                    ),
                )

            if "cantidad" in datos:
                try:
                    cantidad = int(datos.get("cantidad"))
                except (TypeError, ValueError):
                    raise IngresoInvalido("La existencia debe ser un número entero.")
                if cantidad < 0:
                    raise IngresoInvalido("La existencia no puede ser negativa.")
                cursor.execute("UPDATE inventarios SET cantidad = %s WHERE id = %s", (cantidad, inventario_id))
    except IngresoInvalido as e:
        return jsonify(error=e.mensaje), 400

    return jsonify(mensaje="Inventario actualizado."), 200


@admin_bp.route("/inventarios/<int:inventario_id>/traspasar", methods=["POST"])
def inventarios_traspasar(inventario_id):
    """Mueve piezas de esta tienda a otra (cambio de tienda).

    Se suman a la existencia de la tienda destino. Si se mueven todas, el renglón de origen se elimina:
    el producto deja de aparecer en esa tienda (no queda como "agotado").
    """
    datos = request.get_json(silent=True) or {}
    try:
        destino_id = int(datos.get("tienda_destino_id"))
        cantidad = int(datos.get("cantidad"))
    except (TypeError, ValueError):
        return jsonify(error="Indica la tienda destino y cuántas piezas mover."), 400

    try:
        with db_cursor(commit=True) as cursor:
            origen = _inventario_para_editar(cursor, inventario_id)
            if destino_id == origen["tienda_id"]:
                raise IngresoInvalido("Elige una tienda distinta a la actual.")
            cursor.execute("SELECT nombre FROM tiendas WHERE id = %s AND activo = 1", (destino_id,))
            destino = cursor.fetchone()
            if not destino:
                raise IngresoInvalido("La tienda destino no existe o está inactiva.")
            if cantidad <= 0 or cantidad > origen["cantidad"]:
                raise IngresoInvalido(f"Puedes mover de 1 a {origen['cantidad']} piezas.")

            cursor.execute(
                """
                INSERT INTO inventarios (tienda_id, producto_id, cantidad)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE cantidad = cantidad + VALUES(cantidad)
                """,
                (destino_id, origen["producto_id"], cantidad),
            )
            restantes = origen["cantidad"] - cantidad
            if restantes == 0:
                cursor.execute("DELETE FROM inventarios WHERE id = %s", (inventario_id,))
            else:
                cursor.execute("UPDATE inventarios SET cantidad = %s WHERE id = %s", (restantes, inventario_id))
    except IngresoInvalido as e:
        return jsonify(error=e.mensaje), 400

    return jsonify(
        mensaje=f"Se movieron {cantidad} pieza(s) de {origen['tienda']} a {destino['nombre']}.",
        restantes_en_origen=restantes,
    ), 200
