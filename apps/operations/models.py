import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.catalog.models import Product, Promotion


class CashShift(models.Model):
    OPEN = "open"
    CLOSED = "closed"

    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts_opened"
    )
    opened_at = models.DateTimeField(default=timezone.now)
    currency_code = models.CharField(max_length=3)
    opening_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, default=OPEN)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="shifts_closed"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    denominations = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        permissions = [
            ("open_register", "Abrir caja"),
            ("close_register", "Cerrar caja"),
            ("manual_cash_movement", "Registrar entradas y retiros"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["status"],
                condition=models.Q(status="open"),
                name="one_open_shift",
            ),
            models.CheckConstraint(condition=models.Q(opening_amount__gte=0), name="opening_amount_non_negative"),
        ]

    def __str__(self):
        return f"Caja {self.opened_at:%d/%m/%Y %H:%M}"


class CashMovement(models.Model):
    TENDER = "cash_tender"
    CHANGE = "change_out"
    REFUND = "refund_out"
    MANUAL_IN = "manual_in"
    MANUAL_OUT = "manual_out"
    ADJUSTMENT = "adjustment"
    TYPE_CHOICES = [
        (TENDER, "Efectivo recibido"),
        (CHANGE, "Cambio entregado"),
        (REFUND, "Reembolso en efectivo"),
        (MANUAL_IN, "Entrada"),
        (MANUAL_OUT, "Retiro"),
        (ADJUSTMENT, "Corrección auditada"),
    ]
    INCOMING = {TENDER, MANUAL_IN}

    shift = models.ForeignKey(CashShift, on_delete=models.PROTECT, related_name="movements")
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    movement_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    affects_expected = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    currency_code = models.CharField(max_length=3)
    reference = models.CharField(max_length=80, blank=True)
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="cash_movement_positive"),
        ]


class Sale(models.Model):
    CONFIRMED = "confirmed"
    VOIDED = "voided"
    ONLINE = "online"
    OFFLINE = "offline"
    SYNC_ONLINE = "online"
    SYNC_SYNCED = "synced"
    SYNC_ERROR = "error"

    folio = models.CharField(max_length=20, unique=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True, default=None)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    currency_code = models.CharField(max_length=3)
    status = models.CharField(max_length=16, default=CONFIRMED)
    origin = models.CharField(max_length=16, default=ONLINE)
    sync_status = models.CharField(max_length=16, default=SYNC_ONLINE)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    change_given = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shift = models.ForeignKey(CashShift, null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    customer_name = models.CharField(max_length=120, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    catalog_as_of = models.DateTimeField(null=True, blank=True)
    sync_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        permissions = [
            ("sell", "Cobrar ventas"),
            ("void_sale", "Anular ventas"),
            ("view_all_sales", "Consultar todas las ventas"),
            ("view_financial_reports", "Consultar reportes financieros"),
        ]

    def __str__(self):
        return self.folio


class SaleLine(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name_snapshot = models.CharField(max_length=180)
    code_snapshot = models.CharField(max_length=64)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    promotion = models.ForeignKey(Promotion, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="sale_line_qty"),
            models.CheckConstraint(condition=models.Q(discount__gte=0), name="sale_line_discount"),
        ]


class Payment(models.Model):
    CASH = "cash"
    CARD = "card"
    METHOD_CHOICES = [(CASH, "Efectivo"), (CARD, "Tarjeta en terminal externa")]

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=80, blank=True)
    confirmed = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_positive"),
        ]


class ReturnRecord(models.Model):
    CONFIRMED = "confirmed"
    PENDING = "pending"

    folio = models.CharField(max_length=20, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="returns")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    reason = models.CharField(max_length=200)
    refund_method = models.CharField(max_length=16)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    refund_status = models.CharField(max_length=16, default=CONFIRMED)
    external_reference = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("create_return", "Registrar devoluciones"),
        ]


class ExternalRefund(models.Model):
    """Reembolso de tarjeta en una terminal que no controla este sistema."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    VOID = "void"
    RETURN = "return"

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="external_refunds")
    return_record = models.ForeignKey(
        ReturnRecord, null=True, blank=True, on_delete=models.PROTECT, related_name="external_refunds"
    )
    kind = models.CharField(max_length=16)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, default=PENDING)
    reference = models.CharField(max_length=80, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="external_refunds")
    created_at = models.DateTimeField(default=timezone.now)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="external_refunds_confirmed",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ReturnLine(models.Model):
    return_record = models.ForeignKey(ReturnRecord, on_delete=models.PROTECT, related_name="lines")
    sale_line = models.ForeignKey(SaleLine, on_delete=models.PROTECT, related_name="return_lines")
    quantity = models.PositiveIntegerField()
    restock = models.BooleanField(default=True)
    no_restock_reason = models.CharField(max_length=200, blank=True)


class StoreCredit(models.Model):
    customer_name = models.CharField(max_length=120, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    remaining = models.DecimalField(max_digits=12, decimal_places=2)
    origin_label = models.CharField(max_length=40)
    origin_id = models.CharField(max_length=40, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)


class Order(models.Model):
    PENDING = "pending"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (PENDING, "Pendiente"),
        (READY, "Listo"),
        (DELIVERED, "Entregado"),
        (CANCELLED, "Cancelado"),
    ]

    folio = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    customer_name = models.CharField(max_length=120, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    sale = models.ForeignKey(Sale, null=True, blank=True, on_delete=models.PROTECT, related_name="orders")

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("create_order", "Registrar pedidos"),
            ("manage_order", "Cancelar pedidos"),
        ]


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    quoted_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="order_line_qty"),
        ]


class Layaway(models.Model):
    OPEN = "open"
    EXPIRED = "expired"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (OPEN, "Abierto"),
        (EXPIRED, "Vencido"),
        (COMPLETED, "Liquidado"),
        (CANCELLED, "Cancelado"),
    ]

    folio = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=OPEN)
    customer_name = models.CharField(max_length=120, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    policy = models.CharField(max_length=16)
    policy_text = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    sale = models.ForeignKey(Sale, null=True, blank=True, on_delete=models.PROTECT, related_name="layaways")
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("create_layaway", "Registrar apartados"),
            ("manage_layaway", "Cancelar o extender apartados"),
        ]


class LayawayLine(models.Model):
    layaway = models.ForeignKey(Layaway, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="layaway_line_qty"),
        ]


class LayawayPayment(models.Model):
    layaway = models.ForeignKey(Layaway, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=16)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=80, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    shift = models.ForeignKey(CashShift, null=True, blank=True, on_delete=models.PROTECT)


class LayawayAction(models.Model):
    layaway = models.ForeignKey(Layaway, on_delete=models.PROTECT, related_name="actions")
    action = models.CharField(max_length=16)
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    detail = models.TextField(blank=True)


def new_uuid():
    return uuid.uuid4()
