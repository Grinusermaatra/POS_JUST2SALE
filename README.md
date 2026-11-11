# Just2Sale

Punto de venta para un solo negocio. Se instala en una máquina local o en un servidor privado. No es un servicio con registro público, suscripciones ni sucursales.

La bitácora de este trabajo está en [BitacoraPOS.md](BitacoraPOS.md). Ahí está qué ya opera y qué sigue pendiente. Venta, pago, caja y operación sin internet se cierran en las etapas siguientes de este mismo trabajo; no des este sistema por terminado si esa bitácora todavía los marca pendientes.

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

- Superadmin: usuarios, roles, configuración global, módulos e integraciones, además de la operación.
- Supervisor: catálogo, precios, promociones, inventario, insumos y costos. No administra usuarios ni la configuración global.
- Empleado: consulta productos y precios. No ve costos ni el historial de inventario.

Los permisos se comprueban en el servidor.

## Producción

`DJANGO_ENV=production`, `DJANGO_DEBUG=0`, `SECRET_KEY` propia, `ALLOWED_HOSTS` y HTTPS. Si hay un proxy, `BEHIND_PROXY=1`. El respaldo cifrado y el detalle de caja y offline quedan documentados al cerrar la etapa 3.
