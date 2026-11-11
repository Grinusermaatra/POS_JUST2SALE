from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import set_role
from apps.core.bootstrap import sync_roles


class Command(BaseCommand):
    help = "Asigna el rol Superadmin, Supervisor o Empleado a un usuario."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("role", choices=["superadmin", "supervisor", "empleado"])

    def handle(self, *args, **options):
        sync_roles()
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("No existe ese usuario.") from exc
        names = {"superadmin": "Superadmin", "supervisor": "Supervisor", "empleado": "Empleado"}
        set_role(user, names[options["role"]])
        self.stdout.write(self.style.SUCCESS(f"{user.get_username()} ahora es {names[options['role']]}."))
