-- Pedidos con productos fuera de catálogo.
--
-- Una línea de pedido puede no tener producto_id: el cajero solo conoce una
-- descripción genérica y la talla (viene del catálogo del proveedor).
-- /admin le asigna un producto real antes de marcar el pedido como disponible.
--
-- Aplicar sobre una base existente (schema.sql ya incluye estos cambios):
--   docker exec -i matrix-db-1 sh -c 'mysql -u$MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE' < db/migraciones/001_pedidos_fuera_de_catalogo.sql

ALTER TABLE pedido_detalles
    MODIFY producto_id INT NULL,
    ADD COLUMN descripcion VARCHAR(150) NULL AFTER producto_id,
    ADD COLUMN talla VARCHAR(20) NULL AFTER descripcion,
    ADD COLUMN comentario VARCHAR(255) NULL AFTER cantidad;
