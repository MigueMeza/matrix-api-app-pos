-- Apartados entregados.
--
-- 'liquidado' = ya se pagó completo pero el cliente no se lo ha llevado;
-- 'entregado' = se pagó y se entregó (fecha_entrega). En el POS un apartado se
-- ve como vigente (<= 3 meses desde fecha_creacion), expirado (> 3 meses) o
-- entregado; 'cancelado'/'vencido' solo los pone /admin.
--
-- Aplicar sobre una base existente (schema.sql ya incluye estos cambios):
--   docker exec -i matrix-db-1 sh -c 'mysql -u$MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE' < db/migraciones/002_apartados_entregado.sql

ALTER TABLE apartados
    MODIFY estado ENUM('activo','liquidado','entregado','cancelado','vencido') NOT NULL DEFAULT 'activo',
    ADD COLUMN fecha_entrega DATETIME NULL AFTER estado;
