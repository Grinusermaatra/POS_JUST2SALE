import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from cryptography.fernet import Fernet, InvalidToken
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Descifra un respaldo y lo restaura en la base de DATABASE_URL. Detén la aplicación antes."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Ruta del archivo just2sale-*.dump.enc")
        parser.add_argument(
            "--confirmo",
            action="store_true",
            help="Confirma que esta base puede ser reemplazada.",
        )

    def handle(self, *args, **options):
        if not options["confirmo"]:
            raise CommandError("Vuelve a ejecutarlo con --confirmo. La restauración reemplaza objetos de la base.")
        database_url = os.environ.get("DATABASE_URL", "")
        key = os.environ.get("BACKUP_ENCRYPTION_KEY", "")
        source = Path(options["path"])
        if not database_url or not key:
            raise CommandError("Hacen falta DATABASE_URL y BACKUP_ENCRYPTION_KEY.")
        if not source.is_file():
            raise CommandError("No encontré ese archivo.")
        try:
            payload = Fernet(key.encode("utf-8")).decrypt(source.read_bytes())
        except (TypeError, ValueError, InvalidToken) as exc:
            raise CommandError("No se pudo descifrar. Revisa la clave y el archivo.") from exc
        if not payload.startswith(b"PGDMP"):
            raise CommandError("El archivo descifrado no es un volcado de pg_dump.")

        parsed = urlparse(database_url)
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = unquote(parsed.password)
        with tempfile.NamedTemporaryFile(suffix=".dump") as handle:
            handle.write(payload)
            handle.flush()
            result = subprocess.run(
                [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "-h",
                    parsed.hostname or "127.0.0.1",
                    "-p",
                    str(parsed.port or 5432),
                    "-U",
                    unquote(parsed.username or ""),
                    "-d",
                    unquote(parsed.path.lstrip("/")),
                    handle.name,
                ],
                check=False,
                capture_output=True,
                env=env,
            )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace")[-800:]
            raise CommandError(f"pg_restore terminó con error. {detail}")
        self.stdout.write("Restauración terminada. Revisa la aplicación antes de volver a cobrar.")
