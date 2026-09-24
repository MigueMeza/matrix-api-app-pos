--liquibase formatted sql

--changeset matrix:009-create-turnos-caja
--comment: Apertura y corte de caja. Un vendedor solo puede tener un turno abierto (índice único sobre usuario_si_abierto).
-- Un super_admin o un supervisor abre un turno: elige quién vende (un
-- vendedor, o el propio super_admin), la tienda y el fondo inicial.
-- Mientras el turno siga 'abierto', ese vendedor (usuario_id) no puede
-- tener otro turno abierto en ninguna otra tienda (lo garantiza el índice
-- único sobre usuario_si_abierto: solo puede existir una fila 'abierto'
-- por usuario_id, ya que los NULL no chocan en un índice único de MySQL).
-- El corte lo puede hacer cualquier super_admin o supervisor, no
-- necesariamente quien lo abrió, salvo que haya sido el propio super_admin
-- quien vendió, en cuyo caso él mismo puede cerrarlo.
CREATE TABLE turnos_caja (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    usuario_id INT NOT NULL,              -- quién vende (vendedor o el propio super_admin)
    abierto_por INT NOT NULL,             -- super_admin/supervisor que autorizó la apertura
    fondo_inicial DECIMAL(10,2) NOT NULL,
    fecha_apertura DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado ENUM('abierto','cerrado') NOT NULL DEFAULT 'abierto',
    cerrado_por INT NULL,                 -- super_admin/supervisor que hizo el corte
    fondo_final DECIMAL(10,2) NULL,
    fecha_cierre DATETIME NULL,
    notas_cierre VARCHAR(255) NULL,
    usuario_si_abierto INT AS (IF(estado = 'abierto', usuario_id, NULL)) STORED,
    UNIQUE KEY uq_turno_usuario_abierto (usuario_si_abierto),
    KEY idx_turno_usuario_estado (usuario_id, estado),
    CONSTRAINT chk_turno_fondo_inicial CHECK (fondo_inicial >= 0),
    -- ON UPDATE RESTRICT (no CASCADE): usuario_id alimenta la columna generada
    -- usuario_si_abierto, y MySQL no permite CASCADE/SET NULL sobre una
    -- columna de la que depende una columna generada.
    CONSTRAINT fk_turno_tienda
        FOREIGN KEY (tienda_id) REFERENCES tiendas(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_turno_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_turno_abierto_por
        FOREIGN KEY (abierto_por) REFERENCES usuarios(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_turno_cerrado_por
        FOREIGN KEY (cerrado_por) REFERENCES usuarios(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE turnos_caja;

--changeset matrix:009-add-ventas-turno-id
--comment: Cada venta queda ligada al turno de caja en que se hizo.
ALTER TABLE ventas
    ADD COLUMN turno_id INT NULL AFTER usuario_id,
    ADD CONSTRAINT fk_venta_turno
        FOREIGN KEY (turno_id) REFERENCES turnos_caja(id)
        ON DELETE RESTRICT ON UPDATE CASCADE;
--rollback ALTER TABLE ventas DROP FOREIGN KEY fk_venta_turno, DROP COLUMN turno_id;
