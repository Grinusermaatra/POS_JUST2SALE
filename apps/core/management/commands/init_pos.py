from django.core.management.base import BaseCommand

from apps.core.bootstrap import ensure_config, sync_roles


class Command(BaseCommand):
    help = "Crea la configuración del negocio y los roles con sus permisos."

    def handle(self, *args, **options):
        ensure_config()
        sync_roles()
        self.stdout.write(self.style.SUCCESS("Roles y configuración listos."))
