-- Precios de compra / proveedor y configuración del negocio.
--
-- productos.precio sigue siendo el PRECIO DE VENTA. Se agregan:
--   precio_compra             cuánto le costó a la tienda (base del precio sugerido)
--   precio_publico_proveedor  opcional: a cuánto vende el proveedor a sus clientes minoristas
-- configuracion: valores del negocio que el admin puede cambiar sin tocar código.
--   margen_precio_sugerido: precio sugerido = precio de compra + este monto (inicia en $120).
--
-- Aplicar sobre una base existente (schema.sql ya incluye estos cambios):
--   docker exec -i matrix-db-1 sh -c 'mysql -u$MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE' < db/migraciones/003_precios_y_configuracion.sql

ALTER TABLE productos
    ADD COLUMN precio_compra DECIMAL(10,2) NULL AFTER precio,
    ADD COLUMN precio_publico_proveedor DECIMAL(10,2) NULL AFTER precio_compra;

CREATE TABLE configuracion (
    clave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL,
    actualizado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO configuracion (clave, valor) VALUES ('margen_precio_sugerido', '120');
