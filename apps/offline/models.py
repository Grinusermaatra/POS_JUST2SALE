from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.catalog.models import Product
from apps.operations.models import Sale


class Device(models.Model):
    name = models.CharField(max_length=80)
    token_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="devices")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="devices_created"
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("authorize_device", "Autorizar dispositivos para operar sin internet"),
        ]

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class SyncConflict(models.Model):
    OPEN = "open"
    RESOLVED = "resolved"

    kind = models.CharField(max_length=16)
    sale = models.ForeignKey(Sale, null=True, blank=True, on_delete=models.PROTECT, related_name="conflicts")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT)
    message = models.TextField()
    status = models.CharField(max_length=16, default=OPEN)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="conflicts_resolved"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
