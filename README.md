# Just2Sale

Punto de venta para un solo negocio. Se instala en una máquina local o en un servidor privado. No es un servicio con registro público, suscripciones ni sucursales.

La bitácora de este trabajo está en [BitacoraPOS.md](BitacoraPOS.md). Ahí queda qué se comprobó y qué no. Venta, pago, inventario y caja operan. Mercado Libre no está integrado. No se ejecutó la batería formal de pruebas ni un simulacro de restauración.

## Requisitos

- Python 3.12
- PostgreSQL 16

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

En `.env` define `SECRET_KEY` y `DATABASE_URL`. Ejemplo local:

```text
DATABASE_URL=postgres://just2sale:just2sale@127.0.0.1:5432/just2sale
```

La base puede levantarse con Docker, solo en esta máquina:

```bash
docker compose up -d
```

El ejemplo de `docker-compose.yml` trae una contraseña de desarrollo. Cámbiala si el puerto no queda limitado a localhost.

```bash
python manage.py migrate
python manage.py init_pos
python manage.py createsuperuser
python manage.py init_pos
python manage.py runserver
```

El segundo `init_pos` mete al superusuario en el rol Superadmin. Esa cuenta es la propietaria.

También puedes crearla sin escribir la contraseña en el comando:

```bash
OWNER_USERNAME=propietario OWNER_PASSWORD='una frase larga' python manage.py create_owner
```

## Recuperar la cuenta propietaria

Hace falta acceso al servidor.

- Contraseña: `python manage.py changepassword USUARIO`
- Segundo factor perdido: `python manage.py disable_otp USUARIO`
- Rol: `python manage.py assign_role USUARIO superadmin`

No hay recuperación por correo.

## Roles

- Superadmin: usuarios, roles, configuración global, módulos, dispositivos sin internet e integraciones, además de la operación.
- Supervisor: catálogo, precios, promociones, inventario, insumos, costos, caja, devoluciones, anulaciones y reportes. No administra usuarios ni la configuración global.
- Empleado: cobra, consulta productos y precios, registra pedidos y apartados. No ve costos, historial de inventario, reportes financieros, anulaciones ni devoluciones. Abrir y cerrar caja solo si el superadmin lo activa en la configuración global.

Los permisos se comprueban en el servidor.

## Caja

1. Entra con tu usuario.
2. Abre la caja en Caja y anota el fondo inicial. Solo puede haber una caja abierta. La moneda del turno es la de la instalación; no se cambia con la caja abierta.
3. Cobra en Caja. El efectivo puede incluir cambio. La tarjeta queda pagada solo si marcas que la terminal externa ya cobró. Un pago mixto tiene que cubrir el total y el cambio sale del efectivo.
4. El inventario se descuenta al confirmar. La venta no se edita ni se borra.
5. Para cerrar, cuenta las denominaciones. El servidor calcula el total, lo esperado y la diferencia. Ese cierre no se vuelve a editar. Una corrección posterior queda en el historial y no cambia esas tres cifras.
6. Entradas y retiros piden motivo. Un retiro no puede dejar el efectivo esperado en negativo.

Si la caja de una venta ya cerró, anularla o reembolsarla en efectivo exige otra caja abierta. El cierre anterior no se modifica.

El PIN, en Mi cuenta, bloquea la pantalla de caja tras la inactividad configurada. No sustituye la contraseña. Sin PIN no hay bloqueo.

## Sin internet

1. Un superadmin autoriza el dispositivo en Dispositivos y copia el token. Se muestra una sola vez.
2. En la caja, con internet y con la sesión del mismo usuario del token, pega el token y guárdalo en ese navegador. Eso copia productos y precios.
3. Si se va la conexión, la sección Sin internet de la caja permite armar la venta con esa copia y guardarla en el navegador.
4. Al volver internet, Sincronizar pendientes la envía. El mismo identificador local no se cobra dos veces.
5. La venta entra a la caja que esté abierta en ese momento. Si no hay caja abierta, la venta se guarda y queda un conflicto de efectivo; no se altera un cierre ya hecho.
6. Revocar el dispositivo impide sincronizar. Hay 48 horas de gracia después del vencimiento para enviar ventas ya guardadas.

La copia de productos se considera vieja después de las horas configuradas. Conéctate para renovarla antes de seguir cobrando sin internet.

## Reportes

Superadmin y supervisor ven Reportes: día, semana, mes, o un rango, y pueden filtrar por producto, usuario y método. La exportación es CSV o Excel del filtro visible. El empleado recibe un rechazo del servidor. Cada consulta y cada exportación queda en la auditoría.

## Respaldo

Genera una clave y guárdala fuera de la carpeta de respaldos:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

En el entorno del servidor:

```text
BACKUP_DIR=/var/respaldos/just2sale
BACKUP_RETENTION_DAYS=14
BACKUP_ENCRYPTION_KEY=la-clave-generada
```

Cada día, con la aplicación pudiendo seguir en marcha:

```bash
python manage.py backup_db
```

El archivo queda como `just2sale-AAAAMMDD-HHMMSS.dump.enc`. El comando borra los de ese mismo patrón más viejos que la retención. No borra otros archivos.

Para restaurar, detén la aplicación y apunta `DATABASE_URL` a la base que vas a reemplazar:

```bash
python manage.py restore_db /var/respaldos/just2sale/just2sale-AAAAMMDD-HHMMSS.dump.enc --confirmo
```

Eso descifra el volcado y ejecuta `pg_restore --clean`. No crea el rol ni la base vacía: tienen que existir. No se ha hecho un simulacro de restauración en este trabajo. Conserva la clave en otro lugar que el disco de los respaldos; si se pierden juntos, el cifrado no ayuda.

## Producción

`DJANGO_ENV=production`, `DJANGO_DEBUG=0`, `SECRET_KEY` propia, `ALLOWED_HOSTS` y HTTPS. Si hay un proxy, `BEHIND_PROXY=1`. En producción quedan activos CSRF, el límite de intentos de entrada, y las cabeceras CSP, HSTS y X-Frame-Options.

## Límites

- Un negocio, una moneda por instalación mientras la caja está abierta, una caja abierta a la vez.
- La tarjeta es una confirmación del cajero sobre una terminal externa. No hay cobro con número de tarjeta ni Mercado Libre.
- Un paquete tiene su propia existencia. Venderlo no descuenta los componentes. La receta de insumos no se descuenta al vender.
- El cliente, si se anota, es solo nombre y teléfono.
- La venta sin internet usa el precio de la copia local. Si no coincide con el precio del servidor, se conserva el cobrado y queda para revisión.
- La suma de denominaciones en pantalla es una ayuda. Vale la cifra que guarda el servidor al cerrar.
