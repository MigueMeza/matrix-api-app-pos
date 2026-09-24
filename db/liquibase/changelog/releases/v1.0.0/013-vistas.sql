--liquibase formatted sql

--changeset matrix:013-create-v-apartados-resumen runOnChange:true
--comment: runOnChange: al editar la vista en este archivo, Liquibase la vuelve a aplicar (por eso CREATE OR REPLACE).
CREATE OR REPLACE VIEW v_apartados_resumen AS
SELECT
    a.id                AS apartado_id,
    a.cliente_id,
    c.nombre            AS cliente,
    c.categoria         AS categoria_cliente,
    a.estado,
    a.fecha_creacion,
    a.fecha_limite,
    a.total,
    COALESCE(SUM(p.monto), 0)                     AS total_abonado,
    (a.total - COALESCE(SUM(p.monto), 0))         AS saldo_pendiente,
    MIN(p.fecha_pago)                              AS primer_pago,
    MAX(p.fecha_pago)                              AS ultimo_pago,
    DATEDIFF(CURDATE(), DATE(a.fecha_creacion))    AS dias_desde_creacion,
    CASE
        WHEN a.estado = 'activo'
         AND DATEDIFF(CURDATE(), DATE(a.fecha_creacion)) > 90
        THEN 1 ELSE 0
    END                                             AS mayor_a_3_meses,
    CASE
        WHEN a.fecha_limite IS NOT NULL
         AND CURDATE() > a.fecha_limite
        THEN 1 ELSE 0
    END                                             AS vencido_por_fecha_limite
FROM apartados a
JOIN clientes c ON c.id = a.cliente_id
LEFT JOIN apartado_pagos p ON p.apartado_id = a.id
GROUP BY
    a.id, a.cliente_id, c.nombre, c.categoria,
    a.estado, a.fecha_creacion, a.fecha_limite, a.total;
--rollback DROP VIEW v_apartados_resumen;
