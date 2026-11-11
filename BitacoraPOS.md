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

## 2026-11-10 20:49 — Cierre de la etapa 2

Venta, pago, inventario de la venta y caja operan en el servidor. No es el cierre del MVP: faltan reportes, respaldo y la guía completa.

### Qué opera

- Caja en `/caja/`. Buscar producto, armar el carrito y cobrar. El precio es el vigente y la promoción aplicada es una sola, la de mayor descuento por unidad.
- Efectivo con cambio. Tarjeta solo si se confirma el cobro en la terminal externa. El pago mixto cubre el total; el cambio sale solo del efectivo. No se guarda un número de tarjeta.
- Al confirmar, se descuenta la existencia una vez y queda el movimiento. No se vende por debajo de cero ni por debajo de lo apartado.
- Ticket con folio. La venta confirmada no se edita ni se borra.
- Abrir un turno, entradas y retiros con motivo, y cierre por denominaciones. El total lo calcula el servidor. Un segundo cierre no cambia el esperado, el contado ni la diferencia.
- Anular exige motivo, regresa la existencia y registra el efectivo en la caja abierta. No reescribe un cierre ya confirmado. Si la caja de esa venta ya cerró, hace falta otra caja abierta para el reembolso.
- Devolución parcial, con o sin reingreso. No se devuelve más de lo vendido. El reembolso puede ser efectivo, tarjeta externa o saldo a favor.
- Pedido: no mueve inventario hasta que se cobra, y entonces usa el precio vigente.
- Apartado: el anticipo es mayor que cero y menor que el total. Reserva existencia sin descontarla. Se descuenta al liquidar. La política del anticipo queda copiada en el apartado.
- Offline: un superadmin autoriza un dispositivo y el token se muestra una vez. `POST /offline/sincronizar/` guarda la venta con el identificador local. Repetir el mismo identificador no vuelve a descontar. Si no hay caja abierta, la venta se conserva y queda un conflicto de efectivo, sin tocar un cierre. El navegador guarda el token, una copia del catálogo y las ventas locales en IndexedDB, y las envía al volver la conexión. Esa parte del navegador no se recorrió en un navegador.
- Bloqueo de la pantalla de caja con PIN de 4 a 6 dígitos, definido en Mi cuenta. El PIN no inicia sesión. Sin PIN no hay bloqueo.

### Verificación hecha

Cliente HTTP de Django, el 2026-11-10 alrededor de las 20:49, contra PostgreSQL local. Cubrió: abrir caja, venta en efectivo con cambio y descuento de existencia, rechazo de tarjeta sin confirmar y de tarjeta mayor al total, pago mixto, rechazo por falta de existencia, cierre con denominaciones, segundo cierre sin cambiar el conteo, anulación que regresa existencia sin alterar el cierre, devolución que no se duplica, pedido que descuenta solo al cobrar, apartado que reserva sin descontar, sincronización offline idempotente, rechazo sin token, y bloqueo/desbloqueo con PIN. Los usuarios y productos de esa prueba se borraron. No es la batería formal. No se abrió el navegador.

### Límites de esta etapa

- La venta local dentro del navegador (service worker, IndexedDB y la suma en pantalla del cierre) está escrita y no se ejecutó en un navegador.
- Una venta offline se carga a la caja que esté abierta al sincronizar. Si ya no hay caja abierta, no se mete el efectivo a un cierre anterior.
- El descuento offline que supere la promoción vigente se conserva y queda para revisión. No se reescribe la venta.
- Mercado Libre sigue sin implementar.

### Funciones

| Función | Estado |
| --- | --- |
| Autenticación, contraseñas y límite de intentos | implementada |
| Roles y permisos validados en el servidor | implementada |
| Usuarios y recuperación de la cuenta propietaria | implementada |
| 2FA opcional para Superadmin y Supervisor | implementada |
| Bloqueo de caja por inactividad y PIN | implementada |
| Productos, paquetes, precios e historial | implementada |
| Códigos QR y de barras | implementada |
| Promociones | implementada |
| Inventario, alertas e historial | implementada |
| Insumos y recetas, con el módulo apagable | implementada |
| Venta, pagos, ticket e inventario de la venta | implementada |
| Caja, denominaciones, entradas y retiros | implementada |
| Pedidos | implementada |
| Apartados | implementada |
| Devoluciones y anulaciones | implementada |
| Offline y sincronización | implementada |
| Reportes y exportación | pendiente |
| Respaldo cifrado y restauración | pendiente |
| Instalación y documentación de operación | en proceso |
| Integración con terminal de Mercado Libre | pendiente, fase futura, sin simulación |

## 2026-11-10 21:06 — Cierre de la etapa 3

Reportes, instalación, respaldo y la guía de operación quedaron en el repositorio. No se corrió la batería formal ni un simulacro de restauración.

### Qué opera

- Reportes en `/reportes/` para quien tiene el permiso de reportes financieros. Día, semana, mes o un rango, y filtros por producto, usuario y método. El total es de ventas confirmadas. Las anuladas no entran. Las devoluciones del periodo se muestran aparte y no se restan solas. CSV y Excel exportan el filtro visible. Cada consulta y cada exportación queda en la auditoría. El empleado recibe 403.
- `backup_db` hace `pg_dump` en formato custom, lo cifra con Fernet y borra los `just2sale-*.dump.enc` más viejos que `BACKUP_RETENTION_DAYS` (14 si no se dice otra cosa). `restore_db RUTA --confirmo` descifra y ejecuta `pg_restore --clean`. Hay que detener la aplicación y la base de destino ya tiene que existir.
- El README describe instalación, caja, offline, reportes, respaldo y límites.

### Verificación hecha

- Cliente HTTP, alrededor de las 20:54: un superusuario vio la venta del día, descargó CSV y Excel, y un empleado recibió 403. Esas ventas de prueba se borraron.
- `backup_db` escribió un archivo en un directorio temporal, se descifró y el contenido empezaba con el encabezado de `pg_dump`. El archivo se borró. No se restauró ninguna base.
- Navegador, alrededor de las 20:59, con un usuario temporal ya borrado: abrir caja con 100, vender un café de 25 cobrando 50 en efectivo, ticket `V000008` con cambio de 25, cierre con la suma en pantalla, esperado 125, contado 100 y diferencia -25, y el folio en reportes. A 390 px de ancho la pantalla del cierre no se salía del marco. No se recorrió en el navegador la venta guardada en IndexedDB ni la sincronización desde esa pantalla.

### Sigue pendiente

- Mercado Libre, sin simulación.
- Simulacro de restauración sobre una copia de la base.
- La batería de pruebas de abajo. No está ejecutada.

### Pruebas posteriores, en este orden

1. Dos cobros a la vez del mismo producto cuando queda una pieza.
2. Venta sin internet en el navegador: guardar, recargar, sincronizar, repetir el mismo identificador, catálogo viejo, token revocado y caja ya cerrada.
3. Apartado hasta liquidar, vencer, cancelar con cada política de anticipo, y comprobar que la reserva no deja la existencia negativa.
4. Devolución en efectivo con la caja cerrada, sin reingreso, y por encima de lo vendido.
5. Cambio de moneda o decimales con la caja abierta.
6. PIN por inactividad, sin usar el botón de bloquear.
7. Paquete: venderlo no descuenta componentes. La receta no descuenta insumos.
8. Promoción única, la de mayor descuento, sin acumular.
9. Empleado sin costos, sin anular, sin reportes. Supervisor sin usuarios.
10. Restaurar un respaldo en una base vacía de prueba y cobrar después.

### Funciones

| Función | Estado |
| --- | --- |
| Autenticación, contraseñas y límite de intentos | implementada |
| Roles y permisos validados en el servidor | implementada |
| Usuarios y recuperación de la cuenta propietaria | implementada |
| 2FA opcional para Superadmin y Supervisor | implementada |
| Bloqueo de caja por inactividad y PIN | implementada |
| Productos, paquetes, precios e historial | implementada |
| Códigos QR y de barras | implementada |
| Promociones | implementada |
| Inventario, alertas e historial | implementada |
| Insumos y recetas, con el módulo apagable | implementada |
| Venta, pagos, ticket e inventario de la venta | implementada |
| Caja, denominaciones, entradas y retiros | implementada |
| Pedidos | implementada |
| Apartados | implementada |
| Devoluciones y anulaciones | implementada |
| Offline y sincronización | implementada |
| Reportes y exportación | implementada |
| Respaldo cifrado y restauración | implementada; el volcado cifrado se generó y se descifró. La restauración no se ejecutó |
| Instalación y documentación de operación | implementada |
| Integración con terminal de Mercado Libre | pendiente, fase futura, sin simulación |
