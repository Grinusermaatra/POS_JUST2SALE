import os

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import set_role
from apps.core.bootstrap import sync_roles


class Command(BaseCommand):
    help = "Crea la cuenta propietaria con OWNER_USERNAME y OWNER_PASSWORD del entorno."

    def handle(self, *args, **options):
        username = os.environ.get("OWNER_USERNAME", "").strip()
        password = os.environ.get("OWNER_PASSWORD", "")
        email = os.environ.get("OWNER_EMAIL", "").strip()
        if not username or not password:
            raise CommandError("Define OWNER_USERNAME y OWNER_PASSWORD en el entorno. No los pongas en el código.")
        if User.objects.filter(username=username).exists():
            raise CommandError("Ese usuario ya existe. Para recuperar el acceso usa changepassword.")
        user = User(username=username, email=email, is_superuser=True, is_staff=True, is_active=True)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        user.set_password(password)
        user.save()
        sync_roles()
        set_role(user, "Superadmin")
        self.stdout.write(self.style.SUCCESS(f"Cuenta propietaria {username} creada."))
