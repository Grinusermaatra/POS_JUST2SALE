from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Quita el segundo factor de un usuario. Úsalo desde el servidor si perdió el teléfono."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("No existe ese usuario.") from exc
        totp = TOTPDevice.objects.filter(user=user).delete()[0]
        static = StaticDevice.objects.filter(user=user).delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Segundo factor eliminado ({totp} TOTP, {static} códigos)."))
