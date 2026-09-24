--liquibase formatted sql

--changeset matrix:004-create-configuracion
--comment: Valores del negocio que el admin puede cambiar sin tocar código.
CREATE TABLE configuracion (
    clave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL,
    actualizado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE configuracion;

--changeset matrix:004-insert-margen-precio-sugerido
--comment: Precio sugerido = precio de compra + este monto.
INSERT INTO configuracion (clave, valor) VALUES ('margen_precio_sugerido', '120');
--rollback DELETE FROM configuracion WHERE clave = 'margen_precio_sugerido';
