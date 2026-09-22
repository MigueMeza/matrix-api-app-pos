from flask import Blueprint, g, jsonify, request

from ..auth import turno_required
from ..db import db_cursor

apartados_bp = Blueprint("apartados", __name__)


@apartados_bp.route("/apartados", methods=["GET"])
@turno_required
def listar():
    with db_cursor() as cursor:
        cursor.execute("SELECT * FROM v_apartados_resumen ORDER BY fecha_creacion DESC")
        apartados = cursor.fetchall()
        cursor.execute("SELECT id, nombre FROM metodos_pago ORDER BY id")
        metodos_pago = cursor.fetchall()

    for item in apartados:
        if "total" in item:
            item["total"] = float(item["total"])

    return jsonify(apartados=apartados, metodos_pago=metodos_pago), 200


@apartados_bp.route("/apartados/<int:apartado_id>/abonar", methods=["POST"])
@turno_required
def abonar(apartado_id):
    datos = request.get_json(silent=True) or {}
    try:
        monto = float(datos.get("monto", 0))
    except (TypeError, ValueError):
        return jsonify(error="El monto debe ser numérico."), 400

    metodo_pago_id = datos.get("metodo_pago_id")
    referencia = (datos.get("referencia") or "").strip() or None

    if not monto or monto <= 0 or not metodo_pago_id:
        return jsonify(error="Captura un monto y un método de pago válidos."), 400

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            SELECT a.id, a.total, a.estado,
                   COALESCE(SUM(p.monto), 0) AS total_abonado
            FROM apartados a
            LEFT JOIN apartado_pagos p ON p.apartado_id = a.id
            WHERE a.id = %s
            GROUP BY a.id, a.total, a.estado
            FOR UPDATE
            """,
            (apartado_id,),
        )
        apartado = cursor.fetchone()

        if not apartado or apartado["estado"] != "activo":
            return jsonify(error="Este apartado no admite abonos o no existe."), 400

        saldo_pendiente = float(apartado["total"]) - float(apartado["total_abonado"])
        if monto > saldo_pendiente:
            return jsonify(error=f"El abono no puede ser mayor al saldo pendiente (${saldo_pendiente:.2f})."), 400

        cursor.execute(
            """
            INSERT INTO apartado_pagos (apartado_id, turno_id, usuario_id, monto, metodo_pago_id, referencia)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (apartado_id, g.turno["id"], g.turno["usuario_id"], monto, metodo_pago_id, referencia),
        )
        
        nuevo_estado = "activo"
        if monto >= saldo_pendiente:
            cursor.execute("UPDATE apartados SET estado = 'liquidado' WHERE id = %s", (apartado_id,))
            nuevo_estado = "liquidado"

    return jsonify(
        mensaje="Abono registrado correctamente.",
        apartado_id=apartado_id,
        monto_abonado=monto,
        saldo_restante=saldo_pendiente - monto,
        estado=nuevo_estado,
    ), 200