from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.access import require
from apps.accounts.models import UserProfile
from apps.accounts.services import check_pin
from apps.catalog.models import Product
from apps.core.models import get_business
from apps.core.money import money
from apps.operations.carts import add_line, set_qty
from apps.operations.access import can_see_shift
from apps.operations.cashbox import current_shift, expected_cash
from apps.operations.checkout import CheckoutError, confirm_sale
from apps.operations.moneycalc import quote_catalog_line
from apps.operations.stock import available_qty

CART = "pos_cart"


def _lines(request):
    return [dict(line) for line in request.session.get(CART, [])]


def _save(request, lines):
    request.session[CART] = lines
    request.session.modified = True


def _quote(lines, config):
    products = Product.objects.in_bulk([line["product_id"] for line in lines])
    rows = []
    total = money(0, config.decimal_places)
    for line in lines:
        product = products.get(line["product_id"])
        if product is None:
            continue
        quoted = quote_catalog_line(product, int(line["quantity"]), config)
        quoted["available"] = available_qty(product)
        rows.append(quoted)
        total += quoted["line_total"]
    return rows, money(total, config.decimal_places)


def _payments(post):
    rows = []
    cash = (post.get("cash_tendered") or "").strip()
    card = (post.get("card_amount") or "").strip()
    if cash:
        rows.append({"method": "cash", "tendered": cash, "reference": "", "confirmed": True})
    if card:
        rows.append(
            {
                "method": "card",
                "tendered": card,
                "reference": post.get("card_reference", ""),
                "confirmed": post.get("card_confirmed") == "on",
            }
        )
    return rows


def pos_home(request):
    require(request.user, "operations.sell")
    config = getattr(request, "business", None) or get_business()
    query = (request.GET.get("q") or "").strip()
    matches = []
    if query:
        matches = list(
            Product.objects.filter(is_active=True, name__icontains=query).order_by("name")[:12]
        )
        exact = Product.objects.filter(is_active=True, code__iexact=query).first()
        if exact and all(item.pk != exact.pk for item in matches):
            matches.insert(0, exact)
    shift = current_shift()
    rows, total = _quote(_lines(request), config)
    has_pin = UserProfile.objects.filter(user=request.user).exclude(pin_hash="").exists()
    return render(
        request,
        "operations/pos.html",
        {
            "rows": rows,
            "total": total,
            "query": query,
            "matches": matches,
            "shift": shift,
            "can_see_shift": bool(shift and can_see_shift(request.user, shift)),
            "expected": expected_cash(shift, config.decimal_places) if shift else None,
            "has_pin": has_pin,
            "inactivity": config.inactivity_minutes,
        },
    )


@require_POST
def pos_add(request):
    require(request.user, "operations.sell")
    product = None
    if request.POST.get("product_id", "").isdigit():
        product = Product.objects.filter(pk=int(request.POST["product_id"]), is_active=True).first()
    code = (request.POST.get("code") or "").strip()
    if product is None and code:
        product = Product.objects.filter(code__iexact=code, is_active=True).first()
    if product is None:
        messages.error(request, "No encontré ese producto activo.")
        return redirect("pos")
    try:
        quantity = int(request.POST.get("quantity") or 1)
    except ValueError:
        quantity = 0
    if quantity < 1:
        messages.error(request, "La cantidad tiene que ser al menos 1.")
        return redirect("pos")
    lines = add_line(_lines(request), product.pk, quantity)
    wanted = next(line["quantity"] for line in lines if line["product_id"] == product.pk)
    if wanted > available_qty(product):
        messages.error(request, f"No hay suficientes {product.name}. Disponibles: {available_qty(product)}.")
        return redirect("pos")
    _save(request, lines)
    return redirect("pos")


@require_POST
def pos_qty(request):
    require(request.user, "operations.sell")
    try:
        product_id = int(request.POST.get("product_id"))
        quantity = int(request.POST.get("quantity") or 0)
    except (TypeError, ValueError):
        return redirect("pos")
    product = Product.objects.filter(pk=product_id).first()
    if product and quantity > available_qty(product):
        messages.error(request, f"No hay suficientes {product.name}.")
        return redirect("pos")
    _save(request, set_qty(_lines(request), product_id, quantity))
    return redirect("pos")


@require_POST
def pos_clear(request):
    require(request.user, "operations.sell")
    _save(request, [])
    return redirect("pos")


@require_POST
def pos_charge(request):
    require(request.user, "operations.sell")
    config = getattr(request, "business", None) or get_business()
    lines = _lines(request)
    if not lines:
        messages.error(request, "El carrito está vacío.")
        return redirect("pos")
    try:
        sale = confirm_sale(
            user=request.user,
            lines=lines,
            payments=_payments(request.POST),
            shift=current_shift(),
            customer_name=request.POST.get("customer_name", ""),
            customer_phone=request.POST.get("customer_phone", ""),
            config=config,
        )
    except CheckoutError as exc:
        messages.error(request, str(exc))
        return redirect("pos")
    _save(request, [])
    messages.success(request, f"Venta {sale.folio} confirmada.")
    return redirect("ticket", folio=sale.folio)


def register_lock(request):
    require(request.user, "operations.sell")
    return render(request, "operations/lock.html")


@require_POST
def register_block(request):
    require(request.user, "operations.sell")
    if UserProfile.objects.filter(user=request.user).exclude(pin_hash="").exists():
        request.session["register_locked"] = True
    return redirect("register_lock")


@require_POST
def register_unlock(request):
    require(request.user, "operations.sell")
    if check_pin(request.user, request.POST.get("pin", "")):
        request.session["register_locked"] = False
        request.session["register_seen"] = timezone.now().isoformat()
        return redirect("pos")
    messages.error(request, "PIN incorrecto.")
    return redirect("register_lock")
