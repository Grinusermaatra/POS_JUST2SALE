from django.conf import settings
from django.db import models

from apps.catalog.models import Product


class StockMovement(models.Model):
    ENTRY = "entry"
    EXIT = "exit"
    ADJUSTMENT = "adjustment"
    SALE = "sale"
    RETURN_IN = "return_in"
    VOID_IN = "void_in"
    TYPE_CHOICES = [
        (ENTRY, "Entrada"),
        (EXIT, "Salida"),
        (ADJUSTMENT, "Ajuste"),
        (SALE, "Venta"),
        (RETURN_IN, "Devolución"),
        (VOID_IN, "Anulación"),
    ]
    MANUAL_TYPES = {ENTRY, EXIT, ADJUSTMENT}

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    quantity = models.IntegerField()
    movement_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ref_type = models.CharField(max_length=32, blank=True)
    ref_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        permissions = [
            ("adjust_inventory", "Capturar entradas, salidas y ajustes"),
            ("view_inventory_history", "Consultar el historial de inventario"),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity}"


class Supply(models.Model):
    UNIT_CHOICES = [
        ("kg", "Kilogramos"),
        ("l", "Litros"),
        ("g", "Gramos"),
        ("piece", "Piezas"),
    ]

    name = models.CharField(max_length=180)
    unit = models.CharField(max_length=16, choices=UNIT_CHOICES)
    stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        permissions = [
            ("manage_supplies", "Capturar insumos"),
            ("view_costs", "Consultar costos"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(stock__gte=0), name="supply_stock_non_negative"),
        ]

    def __str__(self):
        return self.name


class SupplyMovement(models.Model):
    ENTRY = "entry"
    CONSUMPTION = "consumption"
    ADJUSTMENT = "adjustment"
    TYPE_CHOICES = [
        (ENTRY, "Entrada"),
        (CONSUMPTION, "Consumo"),
        (ADJUSTMENT, "Ajuste"),
    ]

    supply = models.ForeignKey(Supply, on_delete=models.PROTECT, related_name="movements")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    movement_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    ref_type = models.CharField(max_length=32, blank=True)
    ref_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class RecipeLine(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recipe_lines")
    supply = models.ForeignKey(Supply, on_delete=models.PROTECT, related_name="recipe_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "supply"], name="recipe_supply_once"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="recipe_quantity_positive"),
        ]
