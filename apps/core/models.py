from decimal import Decimal

from django.conf import settings
from django.db import models

DENOMINATIONS = {
    "MXN": ["1000", "500", "200", "100", "50", "20", "10", "5", "2", "1", "0.50"],
    "USD": ["100", "50", "20", "10", "5", "1", "0.25", "0.10", "0.05", "0.01"],
}

LAYAWAY_POLICIES = [
    ("refund", "Reembolso del anticipo"),
    ("credit", "Saldo a favor"),
    ("retain", "El anticipo no se devuelve"),
]


class BusinessConfig(models.Model):
    business_name = models.CharField(max_length=120, default="Mi negocio")
    currency_code = models.CharField(max_length=3, default="MXN")
    currency_symbol = models.CharField(max_length=8, default="$")
    decimal_places = models.PositiveSmallIntegerField(default=2)
    denominations = models.JSONField(default=list)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("16.00"))
    prices_include_tax = models.BooleanField(default=True)
    low_stock_default = models.PositiveIntegerField(default=5)
    inactivity_minutes = models.PositiveSmallIntegerField(default=5)
    offline_auth_days = models.PositiveSmallIntegerField(default=7)
    offline_stale_hours = models.PositiveSmallIntegerField(default=24)
    cashiers_may_open_register = models.BooleanField(default=False)
    layaway_policy = models.CharField(max_length=16, default="refund")
    layaway_default_days = models.PositiveSmallIntegerField(default=15)
    supplies_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Configuración"
        permissions = [
            ("change_global_config", "Cambiar la configuración global"),
            ("change_operational_config", "Cambiar parámetros operativos"),
            ("manage_integrations", "Administrar integraciones"),
            ("toggle_modules", "Activar o desactivar módulos"),
            ("view_auditlog", "Consultar la auditoría"),
        ]

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.currency_code not in DENOMINATIONS:
            self.currency_code = "MXN"
        if not self.denominations:
            self.denominations = list(DENOMINATIONS[self.currency_code])
        super().save(*args, **kwargs)

    def __str__(self):
        return self.business_name

    def policy_label(self):
        return dict(LAYAWAY_POLICIES).get(self.layaway_policy, self.layaway_policy)

    def policy_text(self):
        texts = {
            "refund": "Si el apartado se cancela o vence y se cancela, el anticipo se reembolsa.",
            "credit": "Si el apartado se cancela o vence y se cancela, el anticipo queda como saldo a favor.",
            "retain": "Si el apartado se cancela o vence y se cancela, el anticipo no se devuelve.",
        }
        return texts.get(self.layaway_policy, "")


def get_business():
    config = BusinessConfig.objects.filter(pk=1).first()
    if config:
        return config
    config = BusinessConfig(denominations=list(DENOMINATIONS["MXN"]))
    config.save()
    return config


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_logs"
    )
    username_snapshot = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=64, db_index=True)
    object_label = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    detail = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action} {self.created_at:%Y-%m-%d %H:%M}"


class LoginAttempt(models.Model):
    key = models.CharField(max_length=180, unique=True)
    failures = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class Sequence(models.Model):
    name = models.CharField(max_length=32, primary_key=True)
    value = models.PositiveIntegerField(default=0)
