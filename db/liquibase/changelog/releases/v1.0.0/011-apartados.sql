--liquibase formatted sql

--changeset matrix:011-create-apartados
--comment: Producto retenido para un cliente hasta que termine de abonar o expire (3 meses).
-- El producto existe físicamente en la tienda pero está retenido para un
-- cliente hasta que termine de abonar o expire (3 meses). El vencimiento
-- se calcula al vuelo (v_apartados_resumen, /apartados), no cambia `estado` solo.
-- Al apartar, las piezas salen de inventarios (nadie más puede venderlas).
-- 'liquidado' = pagado completo sin entregar, 'entregado' = el cliente ya se
-- lo llevó (fecha_entrega). 'cancelado'/'vencido' solo los pone /admin.
CREATE TABLE apartados (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    cliente_id INT NOT NULL,
    usuario_id INT NOT NULL,              -- quién registró el apartado
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_limite DATE NULL,               -- fecha acordada para liquidar
    total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    anticipo_requerido DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    estado ENUM('activo','liquidado','entregado','cancelado','vencido') NOT NULL DEFAULT 'activo',
    fecha_entrega DATETIME NULL,
    observaciones TEXT NULL,
    CONSTRAINT fk_apartado_tienda
        FOREIGN KEY (tienda_id) REFERENCES tiendas(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_apartado_cliente
        FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_apartado_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE apartados;

--changeset matrix:011-create-apartado-detalles
--comment: Productos del apartado.
CREATE TABLE apartado_detalles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    apartado_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED,
    CONSTRAINT chk_apartado_detalle_cantidad CHECK (cantidad > 0),
    CONSTRAINT fk_apartado_detalle_apartado
        FOREIGN KEY (apartado_id) REFERENCES apartados(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_apartado_detalle_producto
        FOREIGN KEY (producto_id) REFERENCES productos(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE apartado_detalles;

--changeset matrix:011-create-apartado-pagos
--comment: Historial de abonos. turno_id permite que el corte de caja sume los abonos en efectivo.
-- turno_id: turno durante el cual se recibió el abono. Permite que el
-- corte de caja sume los abonos en efectivo igual que hace con venta_pagos.
-- metodo_pago_id: unificado con venta_pagos (ya no es un ENUM aparte).
CREATE TABLE apartado_pagos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    apartado_id INT NOT NULL,
    turno_id INT NULL,
    usuario_id INT NOT NULL,              -- quién recibió el pago
    monto DECIMAL(10,2) NOT NULL,
    metodo_pago_id INT NOT NULL,
    fecha_pago DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    referencia VARCHAR(100) NULL,         -- folio, autorización, etc.
    notas VARCHAR(255) NULL,
    CONSTRAINT chk_apartado_pago_monto CHECK (monto > 0),
    CONSTRAINT fk_apartado_pago_apartado
        FOREIGN KEY (apartado_id) REFERENCES apartados(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_apartado_pago_turno
        FOREIGN KEY (turno_id) REFERENCES turnos_caja(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_apartado_pago_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_apartado_pago_metodo
        FOREIGN KEY (metodo_pago_id) REFERENCES metodos_pago(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE apartado_pagos;
