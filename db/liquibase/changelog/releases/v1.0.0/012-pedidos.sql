--liquibase formatted sql

--changeset matrix:012-create-pedidos
--comment: Prendas que el cliente pide y la tienda consigue con el proveedor.
-- Un pedido nace 'pendiente' cuando cualquier usuario del POS lo registra.
-- Solo /admin puede moverlo a 'disponible' (ya llegó, la mercancía queda
-- reservada para el cliente y NO entra a inventarios) o a 'cancelado' (si ya
-- estaba disponible, sus piezas sí se suman a inventarios). Un pedido 'disponible' puede convertirse en
-- una venta o en un apartado (nunca ambos, ver chk_pedido_conversion_unica).
-- Al convertirse pasa a 'entregado' y queda apuntando a cuál de los dos.
CREATE TABLE pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    cliente_id INT NOT NULL,              -- cliente que solicita la prenda
    usuario_id INT NOT NULL,              -- empleado que registró el pedido

    fecha_pedido DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_disponible DATETIME NULL,       -- cuándo pasó a 'disponible'

    estado ENUM(
        'pendiente',    -- se está intentando conseguir con el proveedor
        'disponible',   -- ya llegó a la tienda, puede convertirse en venta o apartado
        'entregado',    -- ya se convirtió en una venta o un apartado
        'cancelado'     -- no se pudo conseguir / el cliente canceló
    ) NOT NULL DEFAULT 'pendiente',

    venta_id INT NULL,                    -- si se convirtió en una venta directa
    apartado_id INT NULL,                 -- si se convirtió en un apartado

    observaciones TEXT NULL,

    CONSTRAINT chk_pedido_conversion_unica
        CHECK (venta_id IS NULL OR apartado_id IS NULL),

    CONSTRAINT fk_pedido_tienda
        FOREIGN KEY (tienda_id) REFERENCES tiendas(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_pedido_cliente
        FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_pedido_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    -- ON UPDATE RESTRICT (no CASCADE): venta_id/apartado_id participan en
    -- chk_pedido_conversion_unica, y MySQL no permite una acción de FK en
    -- cascada sobre una columna que también tiene un CHECK (error 3823).
    CONSTRAINT fk_pedido_venta
        FOREIGN KEY (venta_id) REFERENCES ventas(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_pedido_apartado
        FOREIGN KEY (apartado_id) REFERENCES apartados(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE pedidos;

--changeset matrix:012-create-pedido-detalles
--comment: Prendas solicitadas, del catálogo (producto_id) o fuera de catálogo (descripcion + talla).
-- Una línea es del catálogo (producto_id) o "fuera de catálogo": el cajero
-- solo conoce una descripción genérica y la talla (ej. "Chamarra de gala", M)
-- porque viene de un catálogo del proveedor. En ese caso producto_id es NULL
-- y /admin debe asignarle un producto real (con precio) antes de marcar el
-- pedido como 'disponible'. La regla "producto_id o descripcion" la valida la
-- API: MySQL no permite un CHECK sobre una columna con FK ON UPDATE CASCADE.
CREATE TABLE pedido_detalles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id INT NOT NULL,
    producto_id INT NULL,
    descripcion VARCHAR(150) NULL,        -- solo fuera de catálogo
    talla VARCHAR(20) NULL,               -- solo fuera de catálogo
    cantidad INT NOT NULL,
    comentario VARCHAR(255) NULL,         -- ej. "puede ser roja o negra"
    CONSTRAINT chk_pedido_detalle_cantidad CHECK (cantidad > 0),
    CONSTRAINT fk_pedido_detalle_pedido
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pedido_detalle_producto
        FOREIGN KEY (producto_id) REFERENCES productos(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--rollback DROP TABLE pedido_detalles;
