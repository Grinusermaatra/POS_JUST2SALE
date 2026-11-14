import hashlib
from datetime import timedelta

from django.utils import timezone

from apps.offline.models import Device


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def device_from_request(request):
    header = request.headers.get("Authorization", "")
    token = ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    token = token or request.headers.get("X-Device-Token", "").strip()
    if not token:
        return None
    return Device.objects.filter(token_hash=hash_token(token)).select_related("user").first()


def device_can_sync(device):
    if device is None or device.revoked_at is not None:
        return False
    return timezone.now() <= device.expires_at + timedelta(hours=48)
