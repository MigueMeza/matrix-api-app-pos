SET NAMES utf8mb4;
-- ============================================================
-- db/schema.sql
-- Esquema de base de datos para sistema de punto de venta (MySQL)
-- Tienda de ropa - incluye ventas, clientes, apartados y pedidos
-- ============================================================

-- ------------------------------------------------------------
-- 1. tiendas
-- ------------------------------------------------------------
CREATE TABLE tiendas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    direccion VARCHAR(255) NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- 2. usuarios
-- ------------------------------------------------------------
-- Solo super_admin y supervisor inician sesión (tienen password_hash).
-- vendedor es un registro sin contraseña: se le asigna una caja, nunca
-- se autentica por sí mismo (ver app/blueprints/caja.py).
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

-- ------------------------------------------------------------
-- 3. productos (cada variante talla/color es su propia fila)
-- ------------------------------------------------------------
CREATE TABLE productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    talla VARCHAR(20) NULL,
    color VARCHAR(50) NULL,
    precio DECIMAL(10,2) NOT NULL,
    codigo_barras VARCHAR(100) NULL UNIQUE,
    activo TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- 4. inventarios (stock por tienda + producto)
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- 5. ventas
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- 6. detalle_ventas
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- 7. metodos_pago (catálogo) — usado por venta_pagos y apartado_pagos
-- ------------------------------------------------------------
CREATE TABLE metodos_pago (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO metodos_pago (id, nombre) VALUES
    (1, 'efectivo'),
    (2, 'transferencia'),
    (3, 'TC/TD'),
    (4, 'otro');

-- ------------------------------------------------------------
-- 8. venta_pagos (uno o varios pagos por venta)
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- 8b. turnos_caja (apertura/corte de caja)
-- ------------------------------------------------------------
-- Un super_admin o un supervisor abre un turno: elige quién vende (un
-- vendedor, o el propio super_admin), la tienda y el fondo inicial.
-- Mientras el turno siga 'abierto', ese vendedor (usuario_id) no puede
-- tener otro turno abierto en ninguna otra tienda (lo garantiza el índice
-- único sobre usuario_si_abierto: solo puede existir una fila 'abierto'
-- por usuario_id, ya que los NULL no chocan en un índice único de MySQL).
-- El corte lo puede hacer cualquier super_admin o supervisor, no
-- necesariamente quien lo abrió — salvo que haya sido el propio super_admin
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

ALTER TABLE ventas
    ADD COLUMN turno_id INT NULL AFTER usuario_id,
    ADD CONSTRAINT fk_venta_turno
        FOREIGN KEY (turno_id) REFERENCES turnos_caja(id)
        ON DELETE RESTRICT ON UPDATE CASCADE;

-- ------------------------------------------------------------
-- 9. clientes (globales, sin tienda_id)
-- ------------------------------------------------------------
CREATE TABLE clientes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    telefono VARCHAR(30) NULL,
    categoria ENUM('estandar','premium') NOT NULL DEFAULT 'estandar',
    notas TEXT NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- 10. índices de clientes
-- ------------------------------------------------------------
CREATE INDEX idx_clientes_telefono ON clientes(telefono);

-- ------------------------------------------------------------
-- 11. apartados (cabecera)
-- ------------------------------------------------------------
-- El producto existe físicamente en la tienda pero está retenido para un
-- cliente hasta que termine de abonar o expire (3 meses) — el vencimiento
-- se calcula al vuelo en v_apartados_resumen, no cambia `estado` solo.
CREATE TABLE apartados (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    cliente_id INT NOT NULL,
    usuario_id INT NOT NULL,              -- quién registró el apartado
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_limite DATE NULL,               -- fecha acordada para liquidar
    total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    anticipo_requerido DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    estado ENUM('activo','liquidado','cancelado','vencido') NOT NULL DEFAULT 'activo',
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

-- ------------------------------------------------------------
-- 12. apartado_detalles (productos del apartado)
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- 13. apartado_pagos (historial de abonos)
-- ------------------------------------------------------------
-- turno_id: turno durante el cual se recibió el abono — permite que el
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

-- ------------------------------------------------------------
-- 14. pedidos (cabecera)
-- ------------------------------------------------------------
-- Un pedido nace 'pendiente' cuando cualquier usuario del POS lo registra.
-- Solo /admin puede moverlo a 'disponible' (ya llegó, se acredita a
-- inventarios) o a 'cancelado'. Un pedido 'disponible' puede convertirse en
-- una venta o en un apartado (nunca ambos, ver chk_pedido_conversion_unica);
-- al convertirse pasa a 'entregado' y queda apuntando a cuál de los dos.
CREATE TABLE pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tienda_id INT NOT NULL,
    cliente_id INT NOT NULL,              -- cliente que solicita la prenda
    usuario_id INT NOT NULL,              -- empleado que registró el pedido

    fecha_pedido DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_disponible DATETIME NULL,       -- cuándo pasó a 'disponible'

    estado ENUM(
        'pendiente',    -- se está intentando conseguir con el proveedor
        'disponible',   -- ya llegó a la tienda; puede convertirse en venta o apartado
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

-- ------------------------------------------------------------
-- 15. pedido_detalles (prendas solicitadas)
-- ------------------------------------------------------------
CREATE TABLE pedido_detalles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL,
    CONSTRAINT chk_pedido_detalle_cantidad CHECK (cantidad > 0),
    CONSTRAINT fk_pedido_detalle_pedido
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pedido_detalle_producto
        FOREIGN KEY (producto_id) REFERENCES productos(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- 16. vista: resumen de apartados
-- ------------------------------------------------------------
CREATE VIEW v_apartados_resumen AS
SELECT
    a.id                AS apartado_id,
    a.cliente_id,
    c.nombre            AS cliente,
    c.categoria         AS categoria_cliente,
    a.estado,
    a.fecha_creacion,
    a.fecha_limite,
    a.total,
    COALESCE(SUM(p.monto), 0)                     AS total_abonado,
    (a.total - COALESCE(SUM(p.monto), 0))         AS saldo_pendiente,
    MIN(p.fecha_pago)                              AS primer_pago,
    MAX(p.fecha_pago)                              AS ultimo_pago,
    DATEDIFF(CURDATE(), DATE(a.fecha_creacion))    AS dias_desde_creacion,
    CASE
        WHEN a.estado = 'activo'
         AND DATEDIFF(CURDATE(), DATE(a.fecha_creacion)) > 90
        THEN 1 ELSE 0
    END                                             AS mayor_a_3_meses,
    CASE
        WHEN a.fecha_limite IS NOT NULL
         AND CURDATE() > a.fecha_limite
        THEN 1 ELSE 0
    END                                             AS vencido_por_fecha_limite
FROM apartados a
JOIN clientes c ON c.id = a.cliente_id
LEFT JOIN apartado_pagos p ON p.apartado_id = a.id
GROUP BY
    a.id, a.cliente_id, c.nombre, c.categoria,
    a.estado, a.fecha_creacion, a.fecha_limite, a.total;


-- ============================================================
-- DATOS DE PRUEBA
-- ============================================================
-- ============================================================
-- DATOS DUMMY PARA DESARROLLO
-- ============================================================
-- Ejecutar DESPUÉS de crear el esquema (tablas + vista).
-- Los IDs son explícitos para que las FKs sean predecibles.
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE pedido_detalles;
TRUNCATE TABLE pedidos;
TRUNCATE TABLE apartado_pagos;
TRUNCATE TABLE apartado_detalles;
TRUNCATE TABLE apartados;
TRUNCATE TABLE detalle_ventas;
TRUNCATE TABLE venta_pagos;
TRUNCATE TABLE ventas;
TRUNCATE TABLE turnos_caja;
TRUNCATE TABLE inventarios;
TRUNCATE TABLE productos;
TRUNCATE TABLE clientes;
TRUNCATE TABLE usuarios;
TRUNCATE TABLE tiendas;
SET FOREIGN_KEY_CHECKS = 1;


-- ------------------------------------------------------------
-- 1. TIENDAS
-- ------------------------------------------------------------
INSERT INTO tiendas (id, nombre, direccion, activo) VALUES
    (1, 'Tienda Centro', 'Av. Principal 123, CDMX',          1),
    (2, 'Tienda Norte',  'Blvd. Norte 456, Monterrey',       1),
    (3, 'Tienda Sur',    'Calz. Sur 789, Puebla',            0);  -- inactiva


-- ------------------------------------------------------------
-- 2. USUARIOS
-- ------------------------------------------------------------
-- Contraseñas (solo para dev, solo super_admin/supervisor tienen):
--   admin_centro (super_admin) -> admin123
--   admin_norte  (supervisor)  -> admin123
-- Los vendedores no tienen usuario/contraseña: un super_admin o un
-- supervisor les abre la caja.
INSERT INTO usuarios (id, tienda_id, nombre, usuario_login, password_hash, rol, activo) VALUES
    (1, 1, 'Ana Superadmin', 'admin_centro',
     'scrypt:32768:8:1$yUWuG6o7QAJZqRzL$88896b61ab086acdd664753edaa8b21bac2e7a87c2cac4a19c658c70197e6bd9676b726ba1f37dbec55e6c37270bee4eb08bd680a4be70bccbc2e72da8daf397',
     'super_admin', 1),
    (2, 1, 'Carlos Vendedor', 'cajero_centro', NULL, 'vendedor', 1),
    (3, 2, 'Laura Vendedora', 'cajero_norte', NULL, 'vendedor', 1),
    (4, 2, 'Diego Supervisor', 'admin_norte',
     'scrypt:32768:8:1$yUWuG6o7QAJZqRzL$88896b61ab086acdd664753edaa8b21bac2e7a87c2cac4a19c658c70197e6bd9676b726ba1f37dbec55e6c37270bee4eb08bd680a4be70bccbc2e72da8daf397',
     'supervisor', 1);


-- ------------------------------------------------------------
-- 3. PRODUCTOS (cada variante talla/color = una fila)
-- ------------------------------------------------------------
INSERT INTO productos (id, nombre, talla, color, precio, codigo_barras, activo) VALUES
    -- Playeras
    (1,  'Playera Básica',        'S',  'Azul',    249.00, '750100000001', 1),
    (2,  'Playera Básica',        'M',  'Azul',    249.00, '750100000002', 1),
    (3,  'Playera Básica',        'L',  'Azul',    249.00, '750100000003', 1),
    (4,  'Playera Básica',        'M',  'Negro',   249.00, '750100000004', 1),
    (5,  'Playera Estampada',     'M',  'Blanco',  299.00, '750100000005', 1),
    -- Pantalones
    (6,  'Pantalón de Mezclilla', '30', 'Índigo',  699.00, '750100000006', 1),
    (7,  'Pantalón de Mezclilla', '32', 'Índigo',  699.00, '750100000007', 1),
    (8,  'Pantalón de Mezclilla', '34', 'Índigo',  699.00, '750100000008', 1),
    (9,  'Pantalón Chino',        '32', 'Beige',   549.00, '750100000009', 1),
    -- Chamarras
    (10, 'Chamarra Ligera',       'M',  'Negro',   899.00, '750100000010', 1),
    (11, 'Chamarra Ligera',       'L',  'Negro',   899.00, '750100000011', 1),
    (12, 'Chamarra de Mezclilla','M',  'Azul',   1099.00, '750100000012', 1),
    -- Accesorios
    (13, 'Cinturón de Piel',      NULL, 'Café',    399.00, '750100000013', 1),
    (14, 'Gorra Deportiva',       NULL, 'Negro',   199.00, '750100000014', 1),
    -- Producto descontinuado (activo = 0)
    (15, 'Sudadera Edición 2024', 'M',  'Gris',    799.00, '750100000015', 0);


-- ------------------------------------------------------------
-- 4. INVENTARIOS (stock por tienda + producto)
-- ------------------------------------------------------------
INSERT INTO inventarios (tienda_id, producto_id, cantidad) VALUES
    -- Tienda Centro (1)
    (1, 1, 15), (1, 2, 20), (1, 3, 10), (1, 4, 8),
    (1, 5, 12), (1, 6, 6),  (1, 7, 5),  (1, 8, 4),
    (1, 9, 7),  (1, 10, 4), (1, 11, 3), (1, 12, 2),
    (1, 13, 10),(1, 14, 25),(1, 15, 0),
    -- Tienda Norte (2)
    (2, 1, 7),  (2, 2, 5),  (2, 4, 3),  (2, 6, 2),
    (2, 7, 4),  (2, 10, 2), (2, 13, 6), (2, 14, 10);


-- ------------------------------------------------------------
-- 5. CLIENTES
-- ------------------------------------------------------------
INSERT INTO clientes (id, nombre, telefono, categoria, notas, activo) VALUES
    (1, 'María López',      '5512345678', 'premium',  'Cliente frecuente, prefiere avisos por WhatsApp', 1),
    (2, 'Juan Pérez',       '5598765432', 'estandar', NULL, 1),
    (3, 'Rosa Martínez',    '5511223344', 'estandar', 'Solo compra en rebajas', 1),
    (4, 'Pedro Sánchez',    '5533445566', 'premium',  'Paga siempre en efectivo', 1),
    (5, 'Lucía Fernández',  '5544556677', 'estandar', NULL, 1),
    (6, 'Miguel Ángel Ruiz','5555667788', 'estandar', 'Cliente problemático con pagos', 1),
    (7, 'Sofía Ramírez',    '5566778899', 'premium',  'VIP desde 2024', 1),
    (8, 'Cliente Inactivo',  NULL,        'estandar', 'Sin datos de contacto', 0);


-- ------------------------------------------------------------
-- 6. VENTAS (directas, ya pagadas)
-- ------------------------------------------------------------
INSERT INTO ventas (id, tienda_id, usuario_id, fecha, total) VALUES
    (1, 1, 2, '2026-09-01 11:15:00', 498.00),   -- 2 playeras
    (2, 1, 2, '2026-09-02 16:40:00', 699.00),   -- 1 pantalón
    (3, 2, 3, '2026-09-03 10:05:00', 1098.00),  -- 2 chinos
    (4, 1, 2, '2026-09-05 13:20:00', 899.00),   -- 1 chamarra
    (5, 2, 3, '2026-09-07 17:50:00', 448.00);   -- 1 gorra + 1 playera estampada

INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario) VALUES
    (1, 2, 2, 249.00),
    (2, 7, 1, 699.00),
    (3, 9, 2, 549.00),
    (4, 10, 1, 899.00),
    (5, 14, 1, 199.00),
    (5, 5, 1, 299.00);


-- ------------------------------------------------------------
-- 7. APARTADOS
-- ------------------------------------------------------------
-- Escenarios cubiertos:
--   #1  Activo, con 2 pagos, dentro de plazo
--   #2  Activo, SIN pagos, creado hace > 3 meses  -> mayor_a_3_meses = 1
--   #3  Activo, con 1 pago, ya pasó fecha_limite  -> vencido_por_fecha_limite = 1
--   #4  Liquidado (saldo 0)
--   #5  Cancelado
--   #6  Activo, creado hace > 3 meses, con pagos parciales
--   #7  Activo, recién creado, con anticipo
--   #8  Vencido (marcado formalmente)
-- ------------------------------------------------------------
INSERT INTO apartados
    (id, tienda_id, cliente_id, usuario_id, fecha_creacion, fecha_limite, total, anticipo_requerido, estado, observaciones) VALUES
    (1, 1, 1, 2, '2026-08-15 10:00:00', '2026-10-15', 1398.00, 200.00, 'activo',    '2 pantalones para boda'),
    (2, 1, 2, 2, '2026-05-01 09:00:00', NULL,         249.00, 100.00, 'activo',    'Cliente nunca volvió'),
    (3, 1, 3, 2, '2026-06-10 12:30:00', '2026-08-10', 899.00, 200.00, 'activo',    'Se pasó de la fecha límite'),
    (4, 2, 4, 3, '2026-07-01 15:00:00', '2026-09-01', 549.00, 100.00, 'liquidado', 'Pagado completo'),
    (5, 1, 5, 2, '2026-07-20 11:00:00', '2026-09-20', 399.00, 100.00, 'cancelado', 'Cliente canceló, se devolvió anticipo'),
    (6, 1, 6, 2, '2026-04-15 09:30:00', NULL,         1099.00, 300.00, 'activo',   'Lleva 5 meses, abonos irregulares'),
    (7, 2, 7, 3, '2026-09-08 16:00:00', '2026-11-08', 998.00, 200.00, 'activo',    'Recién apartado'),
    (8, 1, 2, 2, '2026-03-01 10:00:00', '2026-05-01', 699.00, 200.00, 'vencido',   'Marcado vencido formalmente');


-- ------------------------------------------------------------
-- 8. APARTADO_DETALLES
-- ------------------------------------------------------------
INSERT INTO apartado_detalles (apartado_id, producto_id, cantidad, precio_unitario) VALUES
    -- #1: 2 pantalones de mezclilla = 1398
    (1, 7, 2, 699.00),
    -- #2: 1 playera básica = 249
    (2, 2, 1, 249.00),
    -- #3: 1 chamarra ligera = 899
    (3, 10, 1, 899.00),
    -- #4: 1 pantalón chino = 549
    (4, 9, 1, 549.00),
    -- #5: 1 cinturón = 399
    (5, 13, 1, 399.00),
    -- #6: 1 chamarra de mezclilla = 1099
    (6, 12, 1, 1099.00),
    -- #7: 1 chamarra ligera + 1 gorra = 1098 (pero total dice 998 -> ajustamos precio)
    (7, 10, 1, 899.00),
    (7, 14, 1,  99.00),   -- precio con descuento
    -- #8: 1 pantalón de mezclilla = 699
    (8, 7, 1, 699.00);


-- ------------------------------------------------------------
-- 9. APARTADO_PAGOS (historial de abonos)
-- ------------------------------------------------------------
-- metodo_pago_id: 1=efectivo, 2=transferencia, 3=TC/TD, 4=otro
-- turno_id se deja NULL en los datos de prueba (no hay turnos históricos
-- reales asociados a estos abonos de ejemplo).
INSERT INTO apartado_pagos (apartado_id, usuario_id, monto, metodo_pago_id, fecha_pago, referencia, notas) VALUES
    -- #1: 2 pagos, saldo 898
    (1, 2, 200.00, 1, '2026-08-15 10:05:00', NULL,        'Anticipo'),
    (1, 2, 300.00, 3, '2026-09-01 12:30:00', 'AUTH-001',  'Abono parcial'),

    -- #2: SIN pagos (nunca volvió)

    -- #3: 1 pago, saldo 699, ya vencido por fecha
    (3, 2, 200.00, 1, '2026-06-10 12:35:00', NULL,        'Anticipo'),

    -- #4: 2 pagos, saldo 0 (liquidado)
    (4, 3, 100.00, 1, '2026-07-01 15:05:00', NULL,        'Anticipo'),
    (4, 3, 449.00, 2, '2026-08-20 10:00:00', 'TRF-9921',  'Liquidación'),

    -- #5: 1 pago (anticipo devuelto al cancelar)
    (5, 2, 100.00, 1, '2026-07-20 11:05:00', NULL,        'Anticipo (devuelto)'),

    -- #6: 3 pagos irregulares, saldo 599
    (6, 2, 200.00, 1, '2026-04-15 09:35:00', NULL,        'Anticipo'),
    (6, 2, 150.00, 1, '2026-06-01 14:00:00', NULL,        'Abono'),
    (6, 2, 150.00, 3, '2026-08-10 16:20:00', 'AUTH-777',  'Abono'),

    -- #7: 1 pago (anticipo), saldo 798
    (7, 3, 200.00, 1, '2026-09-08 16:05:00', NULL,        'Anticipo'),

    -- #8: 2 pagos (quedó a medias y se marcó vencido)
    (8, 2, 200.00, 1, '2026-03-01 10:05:00', NULL,        'Anticipo'),
    (8, 2, 100.00, 1, '2026-04-15 11:00:00', NULL,        'Abono');


-- ------------------------------------------------------------
-- 10. PEDIDOS
-- ------------------------------------------------------------
INSERT INTO pedidos (id, tienda_id, cliente_id, usuario_id, fecha_pedido, fecha_disponible, estado, venta_id, apartado_id, observaciones) VALUES
    (1, 1, 1, 2, '2026-09-10 10:00:00', NULL,                 'pendiente', NULL, NULL, 'Cliente pidió playera talla XL, no la manejamos en existencia'),
    (2, 1, 3, 2, '2026-08-20 09:00:00', '2026-08-25 09:00:00','disponible', NULL, NULL, 'Ya llegó, falta que el cliente pase a recogerlo'),
    (3, 2, 4, 3, '2026-09-01 11:00:00', NULL,                 'cancelado', NULL, NULL, 'El cliente ya no lo quiso');

INSERT INTO pedido_detalles (pedido_id, producto_id, cantidad) VALUES
    (1, 5, 1),
    (2, 12, 1),
    (3, 9, 2);
