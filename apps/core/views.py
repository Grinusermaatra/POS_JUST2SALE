from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse

from apps.accounts.access import require
from apps.accounts.roles import role_label
from apps.catalog.models import Product
from apps.core.audit import audit
from apps.core.bootstrap import sync_roles
from apps.core.models import AuditLog, get_business
from apps.core.settings_forms import GlobalSettingsForm, OperationalSettingsForm, default_denominations


def dashboard(request):
    business = getattr(request, "business", None) or get_business()
    label = role_label(request.user)
    low_count = None
    if request.user.has_perm("inventory.view_inventory_history"):
        low_count = sum(1 for product in Product.objects.filter(is_active=True) if product.is_low(business.low_stock_default))
    pos_url = ""
    if request.user.has_perm("operations.sell"):
        try:
            pos_url = reverse("pos")
        except NoReverseMatch:
            pos_url = ""
    return render(
        request,
        "dashboard.html",
        {"role_name": label, "low_count": low_count, "pos_url": pos_url},
    )


def settings_home(request):
    if request.user.has_perm("core.change_global_config"):
        return redirect("settings_global")
    if request.user.has_perm("core.change_operational_config"):
        return redirect("settings_operational")
    require(request.user, "core.change_operational_config")
    return redirect("profile")


def settings_global(request):
    require(request.user, "core.change_global_config")
    business = get_business()
    initial = {
        "business_name": business.business_name,
        "currency_code": business.currency_code,
        "currency_symbol": business.currency_symbol,
        "decimal_places": str(business.decimal_places),
        "denominations": "\n".join(str(item) for item in business.denominations),
        "offline_auth_days": business.offline_auth_days,
        "offline_stale_hours": business.offline_stale_hours,
        "cashiers_may_open_register": business.cashiers_may_open_register,
        "supplies_enabled": business.supplies_enabled,
    }
    form = GlobalSettingsForm(
        request.POST or None,
        initial=None if request.method == "POST" else initial,
        places=business.decimal_places,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        previous_currency = business.currency_code
        previous_supplies = business.supplies_enabled
        previous_cashiers = business.cashiers_may_open_register
        business.business_name = data["business_name"].strip()
        business.currency_code = data["currency_code"]
        business.currency_symbol = data["currency_symbol"].strip() or "$"
        business.decimal_places = data["decimal_places"]
        if business.currency_code != previous_currency:
            business.denominations = default_denominations(business.currency_code, business.decimal_places)
            messages.info(request, "La moneda cambió. Se cargaron sus denominaciones habituales.")
        else:
            business.denominations = data["denominations"]
        business.offline_auth_days = data["offline_auth_days"]
        business.offline_stale_hours = data["offline_stale_hours"]
        business.cashiers_may_open_register = data["cashiers_may_open_register"]
        business.supplies_enabled = data["supplies_enabled"]
        business.save()
        if previous_supplies != business.supplies_enabled:
            state = "activado" if business.supplies_enabled else "desactivado"
            audit(request.user, "module.toggle", business, f"Módulo de insumos {state}.")
        if previous_cashiers != business.cashiers_may_open_register:
            sync_roles(employee_register=business.cashiers_may_open_register)
            state = "puede" if business.cashiers_may_open_register else "ya no puede"
            audit(request.user, "permission.change", business, f"El cajero {state} abrir y cerrar su caja.")
        messages.success(request, "Configuración guardada.")
        return redirect("settings_global")
    return render(request, "core/settings_global.html", {"form": form})


def settings_operational(request):
    require(request.user, "core.change_operational_config")
    business = get_business()
    initial = {
        "tax_rate": business.tax_rate,
        "prices_include_tax": business.prices_include_tax,
        "low_stock_default": business.low_stock_default,
        "inactivity_minutes": business.inactivity_minutes,
        "layaway_policy": business.layaway_policy,
        "layaway_default_days": business.layaway_default_days,
    }
    form = OperationalSettingsForm(request.POST or None, initial=None if request.method == "POST" else initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        business.tax_rate = data["tax_rate"]
        business.prices_include_tax = data["prices_include_tax"]
        business.low_stock_default = data["low_stock_default"]
        business.inactivity_minutes = data["inactivity_minutes"]
        business.layaway_policy = data["layaway_policy"]
        business.layaway_default_days = data["layaway_default_days"]
        business.save()
        messages.success(request, "Parámetros operativos guardados.")
        return redirect("settings_operational")
    return render(
        request,
        "core/settings_ops.html",
        {"form": form, "policy_text": business.policy_text()},
    )


def integrations(request):
    require(request.user, "core.manage_integrations")
    return render(request, "core/integrations.html")


def audit_list(request):
    require(request.user, "core.view_auditlog")
    logs = AuditLog.objects.select_related("user")
    action = (request.GET.get("accion") or "").strip()
    who = (request.GET.get("usuario") or "").strip()
    if action:
        logs = logs.filter(action__icontains=action)
    if who:
        logs = logs.filter(Q(username_snapshot__icontains=who) | Q(user__username__icontains=who))
    page = Paginator(logs, 40).get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "core/audit_list.html",
        {"page": page, "query": params.urlencode(), "action": action, "who": who},
    )
