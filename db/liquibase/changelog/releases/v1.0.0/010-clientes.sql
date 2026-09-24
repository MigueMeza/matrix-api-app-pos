--liquibase formatted sql

--changeset matrix:010-create-clientes
--comment: Clientes globales, sin tienda_id.
CREATE TABLE clientes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    telefono VARCHAR(30) NULL,
    categoria ENUM('estandar','premium') NOT NULL DEFAULT 'estandar',
    notas TEXT NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE clientes;

--changeset matrix:010-create-idx-clientes-telefono
CREATE INDEX idx_clientes_telefono ON clientes(telefono);
--rollback DROP INDEX idx_clientes_telefono ON clientes;
