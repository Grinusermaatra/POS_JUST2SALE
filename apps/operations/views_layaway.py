from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.access import require
from apps.catalog.models import Product
from apps.core.models import get_business
from apps.operations.carts import add_line
from apps.operations.layaway_service import (
    LayawayError,
    add_payment,
    cancel_layaway,
    create_layaway,
    extend_layaway,
    layaway_balance,
    layaway_paid,
    layaway_total,
    refresh_expired,
)
from apps.operations.models import Layaway

DRAFT = "layaway_draft"


def _draft(request):
    return [dict(line) for line in request.session.get(DRAFT, [])]


def layaway_list(request):
    if not (request.user.has_perm("operations.create_layaway") or request.user.has_perm("operations.manage_layaway")):
        require(request.user, "operations.create_layaway")
    refresh_expired()
    status = request.GET.get("estado") or ""
    layaways = Layaway.objects.select_related("user", "sale")
    if status:
        layaways = layaways.filter(status=status)
    return render(
        request,
        "operations/layaway_list.html",
        {"layaways": layaways[:80], "status": status, "can_create": request.user.has_perm("operations.create_layaway")},
    )


def layaway_create(request):
    require(request.user, "operations.create_layaway")
    config = getattr(request, "business", None) or get_business()
    lines = _draft(request)
    products = Product.objects.in_bulk([line["product_id"] for line in lines])
    rows = [{"product": products[line["product_id"]], "quantity": line["quantity"]} for line in lines if line["product_id"] in products]
    if request.method == "POST":
        if request.POST.get("policy_ack") != "on":
            messages.error(request, "Confirma que leíste la política del anticipo.")
        else:
            try:
                layaway = create_layaway(
                    user=request.user,
                    lines=lines,
                    customer_name=request.POST.get("customer_name", ""),
                    customer_phone=request.POST.get("customer_phone", ""),
                    deposit=request.POST.get("deposit") or "0",
                    method=request.POST.get("method") or "cash",
                    reference=request.POST.get("reference", ""),
                    confirmed=request.POST.get("card_confirmed") == "on",
                    config=config,
                )
            except LayawayError as exc:
                messages.error(request, str(exc))
            else:
                request.session[DRAFT] = []
                request.session.modified = True
                messages.success(request, f"Apartado {layaway.folio} registrado. El inventario se descuenta al liquidarlo.")
                return redirect("layaway_detail", folio=layaway.folio)
    return render(request, "operations/layaway_form.html", {"rows": rows, "policy_text": config.policy_text()})


@require_POST
def layaway_add(request):
    require(request.user, "operations.create_layaway")
    code = (request.POST.get("code") or "").strip()
    product = Product.objects.filter(code__iexact=code, is_active=True).first()
    if product is None:
        messages.error(request, "No encontré ese producto.")
    else:
        try:
            quantity = int(request.POST.get("quantity") or 1)
        except ValueError:
            quantity = 1
        request.session[DRAFT] = add_line(_draft(request), product.pk, max(quantity, 1))
        request.session.modified = True
    return redirect("layaway_create")


def layaway_detail(request, folio):
    if not (request.user.has_perm("operations.create_layaway") or request.user.has_perm("operations.manage_layaway")):
        require(request.user, "operations.create_layaway")
    refresh_expired()
    config = getattr(request, "business", None) or get_business()
    layaway = get_object_or_404(Layaway.objects.select_related("sale"), folio=folio)
    return render(
        request,
        "operations/layaway_detail.html",
        {
            "layaway": layaway,
            "lines": layaway.lines.select_related("product"),
            "payments": layaway.payments.all(),
            "total": layaway_total(layaway, config.decimal_places),
            "paid": layaway_paid(layaway, config.decimal_places),
            "balance": layaway_balance(layaway, config.decimal_places),
            "can_pay": request.user.has_perm("operations.create_layaway") and layaway.status == Layaway.OPEN,
            "can_manage": request.user.has_perm("operations.manage_layaway")
            and layaway.status in {Layaway.OPEN, Layaway.EXPIRED},
        },
    )


@require_http_methods(["POST"])
def layaway_pay(request, folio):
    require(request.user, "operations.create_layaway")
    config = getattr(request, "business", None) or get_business()
    layaway = get_object_or_404(Layaway, folio=folio)
    try:
        updated = add_payment(
            layaway=layaway,
            user=request.user,
            method=request.POST.get("method") or "cash",
            amount=request.POST.get("amount") or "0",
            reference=request.POST.get("reference", ""),
            confirmed=request.POST.get("card_confirmed") == "on",
            config=config,
        )
    except LayawayError as exc:
        messages.error(request, str(exc))
        return redirect("layaway_detail", folio=folio)
    if updated.sale_id:
        messages.success(request, f"Apartado liquidado. Venta {updated.sale.folio}.")
        return redirect("ticket", folio=updated.sale.folio)
    messages.success(request, "Pago registrado.")
    return redirect("layaway_detail", folio=folio)


@require_POST
def layaway_cancel(request, folio):
    require(request.user, "operations.manage_layaway")
    config = getattr(request, "business", None) or get_business()
    layaway = get_object_or_404(Layaway, folio=folio)
    try:
        cancel_layaway(layaway=layaway, user=request.user, reason=request.POST.get("reason", ""), config=config)
    except LayawayError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Apartado cancelado. La reserva quedó libre.")
    return redirect("layaway_detail", folio=folio)


@require_POST
def layaway_extend(request, folio):
    require(request.user, "operations.manage_layaway")
    layaway = get_object_or_404(Layaway, folio=folio)
    try:
        extend_layaway(
            layaway=layaway,
            user=request.user,
            days=request.POST.get("days") or 0,
            reason=request.POST.get("reason", ""),
        )
    except LayawayError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Vigencia actualizada.")
    return redirect("layaway_detail", folio=folio)
