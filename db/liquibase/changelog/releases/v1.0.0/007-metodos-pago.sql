--liquibase formatted sql

--changeset matrix:007-create-metodos-pago
--comment: Catálogo usado por venta_pagos y apartado_pagos.
CREATE TABLE metodos_pago (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE metodos_pago;

--changeset matrix:007-insert-metodos-pago
--comment: Datos del catálogo, no de prueba: la API busca 'efectivo' por nombre para el corte de caja.
INSERT INTO metodos_pago (id, nombre) VALUES
    (1, 'efectivo'),
    (2, 'transferencia'),
    (3, 'TC/TD'),
    (4, 'otro');
--rollback DELETE FROM metodos_pago WHERE id IN (1, 2, 3, 4);
