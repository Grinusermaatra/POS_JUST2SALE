from decimal import Decimal

from django import forms

from apps.core.forms import PosForm
from apps.core.models import DENOMINATIONS, LAYAWAY_POLICIES
from apps.core.money import money


class GlobalSettingsForm(PosForm):
    business_name = forms.CharField(label="Nombre del negocio", max_length=120)
    currency_code = forms.ChoiceField(label="Moneda", choices=[("MXN", "MXN"), ("USD", "USD")])
    currency_symbol = forms.CharField(label="Símbolo", max_length=8)
    decimal_places = forms.ChoiceField(label="Decimales", choices=[("2", "2"), ("1", "1"), ("0", "0")])
    denominations = forms.CharField(
        label="Denominaciones",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Una por línea. Para MXN y USD lo normal son 2 decimales.",
    )
    offline_auth_days = forms.IntegerField(label="Días de autorización offline", min_value=1, max_value=30)
    offline_stale_hours = forms.IntegerField(
        label="Horas para avisar precios viejos", min_value=1, max_value=168
    )
    cashiers_may_open_register = forms.BooleanField(
        label="El cajero puede abrir y cerrar su caja", required=False
    )
    supplies_enabled = forms.BooleanField(label="Módulo de insumos activo", required=False)

    def __init__(self, *args, places=2, **kwargs):
        super().__init__(*args, **kwargs)
        self.places = places

    def clean_decimal_places(self):
        return int(self.cleaned_data["decimal_places"])

    def clean_denominations(self):
        places = self.cleaned_data.get("decimal_places", self.places)
        found = []
        raw = self.cleaned_data["denominations"].replace(",", "\n")
        for line in raw.splitlines():
            piece = line.strip()
            if not piece:
                continue
            try:
                amount = money(piece, places)
            except ValueError as exc:
                raise forms.ValidationError("Hay una denominación inválida.") from exc
            if amount <= 0:
                raise forms.ValidationError("Cada denominación tiene que ser mayor que cero.")
            found.append(amount)
        unique = sorted(set(found), reverse=True)
        if not unique:
            raise forms.ValidationError("Indica al menos una denominación.")
        return [f"{item:.{places}f}" for item in unique]


class OperationalSettingsForm(PosForm):
    tax_rate = forms.DecimalField(
        label="Impuesto (%)", min_value=0, max_value=100, decimal_places=2, max_digits=5
    )
    prices_include_tax = forms.BooleanField(label="Los precios ya incluyen el impuesto", required=False)
    low_stock_default = forms.IntegerField(label="Alerta de existencia", min_value=0)
    inactivity_minutes = forms.IntegerField(label="Minutos para bloquear la caja", min_value=1, max_value=120)
    layaway_policy = forms.ChoiceField(label="Política de anticipos", choices=LAYAWAY_POLICIES)
    layaway_default_days = forms.IntegerField(label="Días de vigencia del apartado", min_value=1, max_value=365)

    def clean_tax_rate(self):
        return money(self.cleaned_data["tax_rate"], 2)


def default_denominations(currency_code, places):
    values = []
    for raw in DENOMINATIONS.get(currency_code, DENOMINATIONS["MXN"]):
        values.append(f"{money(raw, places):.{places}f}")
    return values
