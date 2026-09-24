--liquibase formatted sql

--changeset matrix:003-create-productos
--comment: Cada variante talla/color es su propia fila.
CREATE TABLE productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    talla VARCHAR(20) NULL,
    color VARCHAR(50) NULL,
    precio DECIMAL(10,2) NOT NULL,                -- precio de venta
    precio_compra DECIMAL(10,2) NULL,             -- cuánto le costó a la tienda
    precio_publico_proveedor DECIMAL(10,2) NULL,  -- a cuánto lo vende el proveedor al público (opcional)
    codigo_barras VARCHAR(100) NULL UNIQUE,
    activo TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE productos;
