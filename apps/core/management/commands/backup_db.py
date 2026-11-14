import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Crea un volcado cifrado de PostgreSQL y borra los que superan la retención."

    def handle(self, *args, **options):
        database_url = os.environ.get("DATABASE_URL", "")
        key = os.environ.get("BACKUP_ENCRYPTION_KEY", "")
        directory = os.environ.get("BACKUP_DIR", "")
        try:
            retention = int(os.environ.get("BACKUP_RETENTION_DAYS") or "14")
        except ValueError as exc:
            raise CommandError("BACKUP_RETENTION_DAYS tiene que ser un número.") from exc
        if not database_url or not key or not directory:
            raise CommandError("Hacen falta DATABASE_URL, BACKUP_ENCRYPTION_KEY y BACKUP_DIR.")
        if retention < 1:
            raise CommandError("La retención tiene que ser de al menos un día.")
        try:
            fernet = Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise CommandError("BACKUP_ENCRYPTION_KEY no es una clave Fernet válida.") from exc

        parsed = urlparse(database_url)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise CommandError("DATABASE_URL no es de PostgreSQL.")
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = unquote(parsed.password)
        dump = subprocess.run(
            [
                "pg_dump",
                "-h",
                parsed.hostname or "127.0.0.1",
                "-p",
                str(parsed.port or 5432),
                "-U",
                unquote(parsed.username or ""),
                "-d",
                unquote(parsed.path.lstrip("/")),
                "-Fc",
                "--no-owner",
            ],
            check=False,
            capture_output=True,
            env=env,
        )
        if dump.returncode != 0 or not dump.stdout.startswith(b"PGDMP"):
            detail = dump.stderr.decode("utf-8", errors="replace")[-500:]
            raise CommandError(f"pg_dump no produjo un volcado. {detail}")

        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        target = folder / f"just2sale-{stamp}.dump.enc"
        target.write_bytes(fernet.encrypt(dump.stdout))
        cutoff = timezone.now() - timedelta(days=retention)
        removed = 0
        for path in folder.glob("just2sale-*.dump.enc"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.get_current_timezone())
            if modified < cutoff and path != target:
                path.unlink()
                removed += 1
        self.stdout.write(f"Respaldo cifrado: {target}. Archivos viejos borrados: {removed}.")
