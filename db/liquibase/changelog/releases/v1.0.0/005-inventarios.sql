--liquibase formatted sql

--changeset matrix:005-create-inventarios
--comment: Existencias por tienda y producto.
CREATE TABLE inventarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL DEFAULT 0,
    CONSTRAINT chk_inventario_cantidad CHECK (cantidad >= 0),
    CONSTRAINT uq_inventario_tienda_producto UNIQUE (tienda_id, producto_id),
    CONSTRAINT fk_inventario_tienda
        FOREIGN KEY (tienda_id) REFERENCES tiendas(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_inventario_producto
        FOREIGN KEY (producto_id) REFERENCES productos(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE inventarios;
