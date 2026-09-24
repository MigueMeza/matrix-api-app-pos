--liquibase formatted sql

--changeset matrix:002-create-usuarios
--comment: Solo super_admin y supervisor inician sesión con contraseña. vendedor no tiene password_hash.
CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    usuario_login VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NULL,      -- NULL para vendedor
    rol ENUM('vendedor','supervisor','super_admin') NOT NULL DEFAULT 'vendedor',
    activo TINYINT(1) NOT NULL DEFAULT 1,
    CONSTRAINT fk_usuario_tienda
        FOREIGN KEY (tienda_id) REFERENCES tiendas(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE usuarios;
