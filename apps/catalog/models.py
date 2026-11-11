from django.conf import settings
from django.db import models


class Product(models.Model):
    KIND_PRODUCT = "product"
    KIND_PACKAGE = "package"
    KIND_CHOICES = [
        (KIND_PRODUCT, "Producto"),
        (KIND_PACKAGE, "Paquete"),
    ]

    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    code = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.IntegerField(default=0)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_PRODUCT)
    is_active = models.BooleanField(default=True)
    low_stock_threshold = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        permissions = [
            ("consult_products", "Consultar productos y precios"),
            ("manage_catalog", "Capturar productos y paquetes"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(stock__gte=0), name="product_stock_non_negative"),
            models.CheckConstraint(condition=models.Q(price__gt=0), name="product_price_positive"),
        ]

    def __str__(self):
        return self.name

    def threshold(self, default):
        if self.low_stock_threshold is None:
            return default
        return self.low_stock_threshold

    def is_low(self, default):
        return self.is_active and self.stock <= self.threshold(default)


class PackageComponent(models.Model):
    package = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="components")
    component = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="used_in_packages")
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["package", "component"], name="package_component_once"),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="package_component_qty"),
        ]

    def __str__(self):
        return f"{self.package} · {self.component} x{self.quantity}"


class PriceHistory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_history")
    old_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Promotion(models.Model):
    PERCENT = "percent"
    FIXED = "fixed"
    TYPE_CHOICES = [
        (PERCENT, "Porcentaje"),
        (FIXED, "Importe fijo por unidad"),
    ]

    name = models.CharField(max_length=120)
    discount_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    products = models.ManyToManyField(Product, blank=True, related_name="promotions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at", "name"]
        permissions = [
            ("manage_promotions", "Definir promociones"),
        ]

    def __str__(self):
        return self.name
