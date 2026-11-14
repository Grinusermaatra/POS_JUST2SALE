from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import LoginAttempt


def _keys(request, username):
    address = request.META.get("REMOTE_ADDR", "") or "sin-ip"
    return [f"ip:{address}", f"user:{username.strip().lower()}"]


def lock_message(request, username):
    now = timezone.now()
    until = None
    for key in _keys(request, username):
        row = LoginAttempt.objects.filter(key=key).first()
        if row and row.locked_until and row.locked_until > now:
            if until is None or row.locked_until > until:
                until = row.locked_until
    if until is None:
        return ""
    local = timezone.localtime(until)
    return f"Demasiados intentos. Vuelve a probar después de las {local:%H:%M}."


def register_failure(request, username):
    limit = settings.LOGIN_FAILURE_LIMIT
    for key in _keys(request, username):
        LoginAttempt.objects.get_or_create(key=key)
        with transaction.atomic():
            row = LoginAttempt.objects.select_for_update().get(key=key)
            if row.locked_until and row.locked_until <= timezone.now():
                row.failures = 0
                row.locked_until = None
            row.failures += 1
            if row.failures >= limit:
                row.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                row.failures = 0
            row.save(update_fields=["failures", "locked_until", "updated_at"])


def register_success(request, username):
    LoginAttempt.objects.filter(key__in=_keys(request, username)).update(failures=0, locked_until=None)
