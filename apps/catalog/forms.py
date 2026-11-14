import re
from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.catalog.models import Product, Promotion
from apps.core.forms import PosModelForm
from apps.core.money import money

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")


class LocalDateTimeField(forms.DateTimeField):
    widget = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
    input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]

    def prepare_value(self, value):
        if value and timezone.is_aware(value):
            value = timezone.localtime(value)
        return super().prepare_value(value)

    def to_python(self, value):
        parsed = super().to_python(value)
        if parsed and timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed


class ProductForm(PosModelForm):
    initial_quantity = forms.IntegerField(label="Existencia inicial", min_value=0, initial=0, required=False)
    initial_reason = forms.CharField(label="Motivo de la existencia inicial", required=False, max_length=200)
    price_reason = forms.CharField(label="Motivo del cambio de precio", required=False, max_length=200)

    class Meta:
        model = Product
        fields = [
            "name",
            "description",
            "code",
            "kind",
            "price",
            "cost",
            "low_stock_threshold",
            "is_active",
        ]
        labels = {
            "name": "Nombre",
            "description": "Descripción",
            "code": "Código",
            "kind": "Tipo",
            "price": "Precio",
            "cost": "Costo",
            "low_stock_threshold": "Alerta de existencia",
            "is_active": "Activo",
        }
        help_texts = {
            "code": "Letras, números, punto, guion o guion bajo. Si lo dejas vacío se genera uno.",
            "low_stock_threshold": "Vacío usa la alerta general del negocio.",
            "description": "Opcional.",
            "cost": "Solo lo ven Superadmin y Supervisor.",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, show_cost=True, creating=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.creating = creating
        if not creating:
            self.fields.pop("initial_quantity")
            self.fields.pop("initial_reason")
        else:
            self.fields.pop("price_reason")
        if not show_cost and "cost" in self.fields:
            self.fields.pop("cost")

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            return ""
        if not CODE_RE.match(code):
            raise forms.ValidationError("Usa letras, números, punto, guion o guion bajo.")
        return code

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("El precio tiene que ser mayor que cero.")
        return money(price, 2)

    def clean_cost(self):
        cost = self.cleaned_data.get("cost")
        if cost is None:
            return None
        if cost < 0:
            raise forms.ValidationError("El costo no puede ser negativo.")
        return money(cost, 2)

    def clean(self):
        cleaned = super().clean()
        if not self.creating and self.instance.pk and "price" in cleaned:
            old = Product.objects.get(pk=self.instance.pk).price
            if cleaned["price"] != old and not (cleaned.get("price_reason") or "").strip():
                self.add_error("price_reason", "Indica por qué cambia el precio.")
        if self.creating and cleaned.get("initial_quantity"):
            if not (cleaned.get("initial_reason") or "").strip():
                self.add_error("initial_reason", "Indica el motivo de la existencia inicial.")
        return cleaned


class PromotionForm(PosModelForm):
    starts_at = LocalDateTimeField(label="Empieza")
    ends_at = LocalDateTimeField(label="Termina")

    class Meta:
        model = Promotion
        fields = ["name", "discount_type", "discount_value", "starts_at", "ends_at", "is_active", "products"]
        labels = {
            "name": "Nombre",
            "discount_type": "Tipo de descuento",
            "discount_value": "Valor",
            "is_active": "Activa",
            "products": "Productos",
        }
        help_texts = {
            "discount_value": "Porcentaje del 0 al 100, o importe por unidad. No se acumula con otra promoción.",
            "products": "Elige al menos un producto.",
        }
        widgets = {"products": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["products"].queryset = Product.objects.filter(is_active=True).order_by("name")
        if self.instance.pk:
            selected = self.instance.products.all()
            self.fields["products"].queryset = (self.fields["products"].queryset | selected).distinct().order_by("name")

    def clean_discount_value(self):
        value = self.cleaned_data["discount_value"]
        if value < 0:
            raise forms.ValidationError("El descuento no puede ser negativo.")
        return money(value, 2)

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("discount_type")
        value = cleaned.get("discount_value")
        if kind == Promotion.PERCENT and value is not None and value > Decimal("100"):
            self.add_error("discount_value", "El porcentaje no puede pasar de 100.")
        start = cleaned.get("starts_at")
        end = cleaned.get("ends_at")
        if start and end and end <= start:
            self.add_error("ends_at", "La promoción tiene que terminar después de empezar.")
        products = cleaned.get("products")
        if products is not None and products.count() == 0:
            self.add_error("products", "Elige al menos un producto.")
        return cleaned
