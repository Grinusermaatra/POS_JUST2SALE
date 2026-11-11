from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.access import require
from apps.catalog.models import Product
from apps.core.audit import audit
from apps.core.forms import PosForm
from apps.core.models import get_business
from apps.inventory.models import RecipeLine, StockMovement, Supply, SupplyMovement
from apps.inventory.services import (
    InventoryError,
    apply_stock_change,
    apply_supply_change,
    set_counted_stock,
    set_counted_supply,
)
from django import forms


class StockMoveForm(PosForm):
    product = forms.ModelChoiceField(label="Producto", queryset=Product.objects.none())
    mode = forms.ChoiceField(
        label="Tipo",
        choices=[
            ("entry", "Entrada"),
            ("exit", "Salida"),
            ("adjustment", "Ajuste a existencia contada"),
        ],
    )
    quantity = forms.IntegerField(label="Cantidad", min_value=0)
    reason = forms.CharField(label="Motivo", max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.order_by("name")
        self.fields["mode"].help_text = "En un ajuste, la cantidad es la existencia contada, no la diferencia."


class SupplyForm(PosForm):
    name = forms.CharField(label="Nombre", max_length=180)
    unit = forms.ChoiceField(label="Unidad", choices=Supply.UNIT_CHOICES)
    cost = forms.DecimalField(label="Costo", required=False, min_value=0, decimal_places=2, max_digits=12)
    is_active = forms.BooleanField(label="Activo", required=False, initial=True)


class SupplyMoveForm(PosForm):
    mode = forms.ChoiceField(
        label="Tipo",
        choices=[
            ("entry", "Entrada"),
            ("consumption", "Consumo"),
            ("adjustment", "Ajuste a existencia contada"),
        ],
    )
    quantity = forms.DecimalField(label="Cantidad", min_value=0, decimal_places=3, max_digits=12)
    reason = forms.CharField(label="Motivo", max_length=200)


def _querystring(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def movement_list(request):
    require(request.user, "inventory.view_inventory_history")
    movements = StockMovement.objects.select_related("product", "user")
    product_id = request.GET.get("producto") or ""
    kind = request.GET.get("tipo") or ""
    if product_id.isdigit():
        movements = movements.filter(product_id=int(product_id))
    if kind:
        movements = movements.filter(movement_type=kind)
    page = Paginator(movements, 30).get_page(request.GET.get("page") or 1)
    return render(
        request,
        "inventory/movement_list.html",
        {
            "page": page,
            "query": _querystring(request),
            "products": Product.objects.order_by("name"),
            "types": StockMovement.TYPE_CHOICES,
            "product_id": product_id,
            "kind": kind,
            "can_adjust": request.user.has_perm("inventory.adjust_inventory"),
        },
    )


def movement_create(request):
    require(request.user, "inventory.adjust_inventory")
    form = StockMoveForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        product = form.cleaned_data["product"]
        mode = form.cleaned_data["mode"]
        quantity = form.cleaned_data["quantity"]
        reason = form.cleaned_data["reason"].strip()
        try:
            if mode == "adjustment":
                movement = set_counted_stock(product=product, counted=quantity, reason=reason, user=request.user)
                if movement is None:
                    messages.info(request, "La existencia ya coincide con lo contado.")
                    return redirect("movement_list")
            elif mode == "entry":
                if quantity < 1:
                    raise InventoryError("La entrada tiene que ser de al menos 1.")
                apply_stock_change(
                    product=product,
                    quantity_delta=quantity,
                    movement_type=StockMovement.ENTRY,
                    reason=reason,
                    user=request.user,
                    ref_type="manual",
                )
            else:
                if quantity < 1:
                    raise InventoryError("La salida tiene que ser de al menos 1.")
                apply_stock_change(
                    product=product,
                    quantity_delta=-quantity,
                    movement_type=StockMovement.EXIT,
                    reason=reason,
                    user=request.user,
                    ref_type="manual",
                )
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            audit(request.user, "inventory.adjust", product, f"{mode} {quantity}. {reason}")
            messages.success(request, "Movimiento registrado.")
            return redirect("movement_list")
    return render(request, "inventory/movement_form.html", {"form": form, "title": "Movimiento de inventario"})


def alerts(request):
    require(request.user, "inventory.view_inventory_history")
    business = getattr(request, "business", None) or get_business()
    default = business.low_stock_default
    rows = []
    for product in Product.objects.filter(is_active=True).order_by("stock", "name"):
        if product.is_low(default):
            product.alert_at = product.threshold(default)
            rows.append(product)
    return render(
        request,
        "inventory/alerts.html",
        {"rows": rows, "default": default, "can_adjust": request.user.has_perm("inventory.adjust_inventory")},
    )


def _supplies_open(request):
    business = getattr(request, "business", None) or get_business()
    if not business.supplies_enabled:
        return render(request, "inventory/supplies_disabled.html", {"business": business}, status=403)
    if not (
        request.user.has_perm("inventory.manage_supplies") or request.user.has_perm("inventory.view_costs")
    ):
        require(request.user, "inventory.manage_supplies")
    return None


def supply_list(request):
    blocked = _supplies_open(request)
    if blocked:
        return blocked
    supplies = Supply.objects.all()
    return render(
        request,
        "inventory/supply_list.html",
        {
            "supplies": supplies,
            "show_cost": request.user.has_perm("inventory.view_costs"),
            "can_manage": request.user.has_perm("inventory.manage_supplies"),
        },
    )


def supply_create(request):
    require(request.user, "inventory.manage_supplies")
    blocked = _supplies_open(request)
    if blocked:
        return blocked
    form = SupplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        supply = Supply.objects.create(
            name=form.cleaned_data["name"].strip(),
            unit=form.cleaned_data["unit"],
            cost=form.cleaned_data["cost"],
            is_active=form.cleaned_data["is_active"],
        )
        messages.success(request, "Insumo guardado. Vender un producto no lo descuenta.")
        return redirect("supply_detail", pk=supply.pk)
    return render(request, "inventory/supply_form.html", {"form": form, "title": "Nuevo insumo"})


def supply_edit(request, pk):
    require(request.user, "inventory.manage_supplies")
    blocked = _supplies_open(request)
    if blocked:
        return blocked
    supply = get_object_or_404(Supply, pk=pk)
    initial = {
        "name": supply.name,
        "unit": supply.unit,
        "cost": supply.cost,
        "is_active": supply.is_active,
    }
    form = SupplyForm(request.POST or None, initial=None if request.method == "POST" else initial)
    if not request.user.has_perm("inventory.view_costs"):
        form.fields.pop("cost", None)
    if request.method == "POST" and form.is_valid():
        supply.name = form.cleaned_data["name"].strip()
        supply.unit = form.cleaned_data["unit"]
        supply.is_active = form.cleaned_data["is_active"]
        if "cost" in form.cleaned_data:
            supply.cost = form.cleaned_data["cost"]
        supply.save()
        messages.success(request, "Insumo actualizado.")
        return redirect("supply_detail", pk=supply.pk)
    return render(request, "inventory/supply_form.html", {"form": form, "title": f"Editar {supply.name}"})


def supply_detail(request, pk):
    blocked = _supplies_open(request)
    if blocked:
        return blocked
    supply = get_object_or_404(Supply, pk=pk)
    movements = supply.movements.select_related("user")[:40]
    return render(
        request,
        "inventory/supply_detail.html",
        {
            "supply": supply,
            "movements": movements,
            "show_cost": request.user.has_perm("inventory.view_costs"),
            "can_manage": request.user.has_perm("inventory.manage_supplies"),
        },
    )


def supply_move(request, pk):
    require(request.user, "inventory.manage_supplies")
    blocked = _supplies_open(request)
    if blocked:
        return blocked
    supply = get_object_or_404(Supply, pk=pk)
    form = SupplyMoveForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        mode = form.cleaned_data["mode"]
        quantity = form.cleaned_data["quantity"]
        try:
            if mode == "adjustment":
                movement = set_counted_supply(
                    supply=supply, counted=quantity, reason=form.cleaned_data["reason"], user=request.user
                )
                if movement is None:
                    messages.info(request, "La existencia ya coincide con lo contado.")
                    return redirect("supply_detail", pk=supply.pk)
            elif mode == "entry":
                if quantity <= 0:
                    raise InventoryError("La entrada tiene que ser mayor que cero.")
                apply_supply_change(
                    supply=supply,
                    quantity_delta=quantity,
                    movement_type=SupplyMovement.ENTRY,
                    reason=form.cleaned_data["reason"],
                    user=request.user,
                )
            else:
                if quantity <= 0:
                    raise InventoryError("El consumo tiene que ser mayor que cero.")
                apply_supply_change(
                    supply=supply,
                    quantity_delta=-quantity,
                    movement_type=SupplyMovement.CONSUMPTION,
                    reason=form.cleaned_data["reason"],
                    user=request.user,
                )
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            audit(request.user, "inventory.adjust", supply, f"Insumo {mode} {quantity}.")
            messages.success(request, "Movimiento de insumo registrado.")
            return redirect("supply_detail", pk=supply.pk)
    return render(request, "inventory/supply_move.html", {"form": form, "supply": supply})


@require_http_methods(["GET", "POST"])
def recipe_edit(request, product_id):
    require(request.user, "inventory.manage_supplies")
    business = getattr(request, "business", None) or get_business()
    product = get_object_or_404(Product, pk=product_id)
    if not business.supplies_enabled:
        return render(request, "inventory/supplies_disabled.html", {"business": business}, status=403)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "remove":
            RecipeLine.objects.filter(product=product, pk=request.POST.get("line_id")).delete()
            messages.success(request, "Insumo quitado de la receta.")
        else:
            supply = Supply.objects.filter(pk=request.POST.get("supply"), is_active=True).first()
            try:
                quantity = Decimal(str(request.POST.get("quantity") or "").replace(",", "."))
            except (InvalidOperation, ValueError):
                quantity = Decimal("0")
            if supply is None:
                messages.error(request, "Elige un insumo.")
            elif quantity <= 0:
                messages.error(request, "La cantidad de la receta tiene que ser mayor que cero.")
            else:
                RecipeLine.objects.update_or_create(
                    product=product, supply=supply, defaults={"quantity": quantity}
                )
                messages.success(request, "Receta guardada. Vender el producto no descuenta el insumo.")
        return redirect("recipe_edit", product_id=product.pk)
    lines = product.recipe_lines.select_related("supply")
    return render(
        request,
        "inventory/recipe_form.html",
        {"product": product, "lines": lines, "supplies": Supply.objects.filter(is_active=True)},
    )
