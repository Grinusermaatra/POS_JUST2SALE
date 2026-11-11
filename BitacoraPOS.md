# Bitácora Just2Sale

Zona horaria de todos los registros: America/Mexico_City.

## 2026-11-10 20:00 — Inicio y estado inicial

### Qué hay en el repositorio

- Un solo commit, `Initial commit`.
- El único archivo de aplicación es `README.md`, con el título `# POS_JUST2SALE`.
- No hay modelos, pantallas, dependencias, instrucciones de arquitectura ni convenciones de código.
- El prototipo HTML experimental no está en este repositorio. No se va a buscar, copiar ni implementar.

### Arquitectura que se va a construir

Instalación de un solo negocio, en la máquina local o en un servidor privado. No hay registro público, suscripciones, multi-negocio ni multi-sucursal.

- Django y PostgreSQL. El dinero se calcula con `Decimal`, nunca con punto flotante.
- Grupos y permisos nativos de Django. Cada acción se valida en el servidor.
- Interfaz servida por Django, en español, usable en computadora y teléfono.
- Color principal `#BB8744`, fondo `#F5F1EA`.
- Moneda inicial MXN. USD queda como alternativa de la instalación, una moneda por venta y por turno.
- La operación en línea (venta, pago, inventario y caja) funciona con formularios en el servidor, aunque el navegador no ejecute JavaScript.
- Sin conexión: aplicación web instalable en el navegador (service worker e IndexedDB) solo en un dispositivo autorizado antes, con ventas locales de identificador único y sincronización idempotente. El detalle se cierra en la etapa 2.
- Secretos solo en variables de entorno.
- Zona horaria de la aplicación: America/Mexico_City.

### Decisiones

- El cajero ve la existencia disponible porque la necesita para cobrar. No ve costos, historial de inventario ni ajustes.
- Un paquete tiene existencia propia. Venderlo no descuenta sus componentes. La composición queda guardada. Armar un paquete es una entrada de inventario.
- La receta producto–insumo se guarda y no descuenta insumos al vender.
- No se borra un usuario con ventas u otros movimientos: se desactiva. Hace falta conservar quién operó.
- Mercado Libre no se integra ni se simula.
- Las pruebas formales no se ejecutan en este trabajo. Al final queda su lista priorizada. Una verificación de humo, si se corre, se anota aparte y no sustituye esa lista.

### Funciones

| Función | Estado |
| --- | --- |
| Autenticación, contraseñas y límite de intentos | pendiente |
| Roles y permisos validados en el servidor | pendiente |
| Usuarios y recuperación de la cuenta propietaria | pendiente |
| 2FA opcional para Superadmin y Supervisor | pendiente |
| Bloqueo de caja por inactividad y PIN | pendiente |
| Productos, paquetes, precios e historial | pendiente |
| Códigos QR y de barras | pendiente |
| Promociones | pendiente |
| Inventario, alertas e historial | pendiente |
| Insumos y recetas, con el módulo apagable | pendiente |
| Venta, pagos, ticket e inventario de la venta | pendiente |
| Caja, denominaciones, entradas y retiros | pendiente |
| Pedidos | pendiente |
| Apartados | pendiente |
| Devoluciones y anulaciones | pendiente |
| Offline y sincronización | pendiente |
| Reportes y exportación | pendiente |
| Respaldo cifrado y restauración | pendiente |
| Instalación y documentación de operación | pendiente |
| Integración con terminal de Mercado Libre | pendiente, fase futura, sin simulación |

### Límites ya visibles

- No hay batería formal de pruebas ejecutada.
- El MVP no está listo: venta, pago, inventario y caja todavía no operan.

## 2026-11-10 20:27 — Cierre de la etapa 1

La base quedó instalable: Django 5.2, PostgreSQL, roles y el catálogo. No incluye todavía la caja.

### Qué opera

- Entrada con usuario y contraseña, validadores de Django (mínimo 10 caracteres) y bloqueo tras 5 intentos por usuario y por IP durante 15 minutos.
- Roles Superadmin, Supervisor y Empleado. Las pantallas niegan la acción en el servidor, no solo ocultan el enlace.
- Alta, edición y baja de usuarios. Si el usuario ya tiene historial, no se borra: se desactiva. La cuenta propietaria del servidor no se degrada desde la web.
- Recuperación en el servidor: `changepassword`, `disable_otp`, `assign_role`, `create_owner`.
- Segundo factor opcional (TOTP y códigos de un solo uso) para Superadmin y Supervisor.
- Productos y paquetes, precio con historial y motivo, códigos QR y de barras para imprimir o descargar.
- Promociones con vigencia y productos. No se acumulan: al cobrar se usará la que más descuente.
- Entradas, salidas y ajustes de inventario con motivo, usuario y hora. No dejan la existencia en negativo.
- Alertas configurables. El cajero ve la existencia y el precio, no el costo ni el historial.
- Insumos, consumos, ajustes y receta. Apagar el módulo bloquea esas pantallas y conserva los datos. Vender no descuenta insumos.
- Configuración global y operativa. Integración de Mercado Libre descrita como no implementada, sin simulación.
- Auditoría de cambios de precio, promoción, inventario manual, permisos y encendido del módulo.

### Verificación hecha

Cliente HTTP de Django, el 2026-11-10 alrededor de las 20:27. Cubrió entrada, rechazos por rol, alta de producto, existencia que no baja de cero, cambio de precio sin tocar la existencia, PNG de código de barras, promoción, composición de paquete, apagado de insumos y segundo factor con código de respaldo. No es la batería formal. Falta recorrer las pantallas en el navegador junto con la caja.

### Sigue pendiente

El bloqueo de la caja por inactividad y el PIN: el gancho está, la pantalla no. Venta, pagos, ticket, caja, pedidos, apartados, devoluciones, anulaciones, offline, reportes, respaldo y la guía completa de operación.

### Funciones

| Función | Estado |
| --- | --- |
| Autenticación, contraseñas y límite de intentos | implementada |
| Roles y permisos validados en el servidor | implementada |
| Usuarios y recuperación de la cuenta propietaria | implementada |
| 2FA opcional para Superadmin y Supervisor | implementada |
| Bloqueo de caja por inactividad y PIN | pendiente |
| Productos, paquetes, precios e historial | implementada |
| Códigos QR y de barras | implementada |
| Promociones | implementada |
| Inventario, alertas e historial | implementada |
| Insumos y recetas, con el módulo apagable | implementada |
| Venta, pagos, ticket e inventario de la venta | pendiente |
| Caja, denominaciones, entradas y retiros | pendiente |
| Pedidos | pendiente |
| Apartados | pendiente |
| Devoluciones y anulaciones | pendiente |
| Offline y sincronización | pendiente |
| Reportes y exportación | pendiente |
| Respaldo cifrado y restauración | pendiente |
| Instalación y documentación de operación | en proceso |
| Integración con terminal de Mercado Libre | pendiente, fase futura, sin simulación |
