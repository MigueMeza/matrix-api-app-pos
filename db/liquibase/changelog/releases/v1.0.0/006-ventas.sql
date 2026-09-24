--liquibase formatted sql

--changeset matrix:006-create-ventas
CREATE TABLE ventas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    usuario_id INT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    CONSTRAINT fk_venta_tienda
        FOREIGN KEY (tienda_id) REFERENCES tiendas(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_venta_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE ventas;

--changeset matrix:006-create-detalle-ventas
CREATE TABLE detalle_ventas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    venta_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED,
    CONSTRAINT chk_detalle_ventas_cantidad CHECK (cantidad > 0),
    CONSTRAINT fk_detalle_venta_venta
        FOREIGN KEY (venta_id) REFERENCES ventas(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_detalle_ventas_productos
        FOREIGN KEY (producto_id) REFERENCES productos(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE detalle_ventas;
