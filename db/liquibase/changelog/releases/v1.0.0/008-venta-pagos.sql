--liquibase formatted sql

--changeset matrix:008-create-venta-pagos
--comment: Uno o varios pagos por venta.
CREATE TABLE venta_pagos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    venta_id INT NOT NULL,
    metodo_pago_id INT NOT NULL,
    monto DECIMAL(10,2) NOT NULL,
    CONSTRAINT chk_venta_pago_monto CHECK (monto > 0),
    CONSTRAINT fk_venta_pago_venta
        FOREIGN KEY (venta_id) REFERENCES ventas(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_venta_pago_metodo
        FOREIGN KEY (metodo_pago_id) REFERENCES metodos_pago(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE venta_pagos;
