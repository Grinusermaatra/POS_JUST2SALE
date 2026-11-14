from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.access import require
from apps.catalog.models import Product
from apps.core.models import get_business
from apps.operations.carts import add_line, set_qty
from apps.operations.cashbox import current_shift
from apps.operations.checkout import CheckoutError, confirm_sale
from apps.operations.folios import next_folio
from apps.operations.models import Order, OrderLine
from apps.operations.views_pos import _payments

DRAFT = "order_draft"


def _draft(request):
    return [dict(line) for line in request.session.get(DRAFT, [])]


def _save(request, lines):
    request.session[DRAFT] = lines
    request.session.modified = True


def order_list(request):
    if not (request.user.has_perm("operations.create_order") or request.user.has_perm("operations.manage_order")):
        require(request.user, "operations.create_order")
    orders = Order.objects.select_related("user", "sale")
    status = request.GET.get("estado") or ""
    if status:
        orders = orders.filter(status=status)
    return render(
        request,
        "operations/order_list.html",
        {"orders": orders[:80], "status": status, "can_create": request.user.has_perm("operations.create_order")},
    )


def order_create(request):
    require(request.user, "operations.create_order")
    lines = _draft(request)
    products = Product.objects.in_bulk([line["product_id"] for line in lines])
    rows = []
    for line in lines:
        product = products.get(line["product_id"])
        if product:
            rows.append({"product": product, "quantity": line["quantity"]})
    return render(request, "operations/order_form.html", {"rows": rows})


@require_POST
def order_add(request):
    require(request.user, "operations.create_order")
    code = (request.POST.get("code") or "").strip()
    product = Product.objects.filter(code__iexact=code, is_active=True).first()
    if product is None and request.POST.get("product_id", "").isdigit():
        product = Product.objects.filter(pk=int(request.POST["product_id"]), is_active=True).first()
    if product is None:
        messages.error(request, "No encontré ese producto.")
        return redirect("order_create")
    try:
        quantity = int(request.POST.get("quantity") or 1)
    except ValueError:
        quantity = 1
    _save(request, add_line(_draft(request), product.pk, max(quantity, 1)))
    return redirect("order_create")


@require_POST
def order_save(request):
    require(request.user, "operations.create_order")
    lines = _draft(request)
    if not lines:
        messages.error(request, "El pedido no tiene productos.")
        return redirect("order_create")
    phone = (request.POST.get("customer_phone") or "").strip()
    if phone and not all(char.isdigit() or char in "+-() " for char in phone):
        messages.error(request, "El teléfono solo puede tener números, espacios, + y guiones.")
        return redirect("order_create")
    with transaction.atomic():
        order = Order.objects.create(
            folio=next_folio("P", "order"),
            customer_name=(request.POST.get("customer_name") or "").strip()[:120],
            customer_phone=phone[:20],
            notes=(request.POST.get("notes") or "").strip(),
            user=request.user,
        )
        products = Product.objects.in_bulk([line["product_id"] for line in lines])
        for line in lines:
            product = products.get(line["product_id"])
            if product is None:
                continue
            OrderLine.objects.create(order=order, product=product, quantity=line["quantity"], quoted_price=product.price)
    _save(request, [])
    messages.success(request, f"Pedido {order.folio} registrado. Todavía no descuenta inventario.")
    return redirect("order_detail", folio=order.folio)


def order_detail(request, folio):
    if not (request.user.has_perm("operations.create_order") or request.user.has_perm("operations.manage_order")):
        require(request.user, "operations.create_order")
    order = get_object_or_404(Order.objects.select_related("sale", "user"), folio=folio)
    return render(
        request,
        "operations/order_detail.html",
        {
            "order": order,
            "lines": order.lines.select_related("product"),
            "can_cancel": request.user.has_perm("operations.manage_order") and order.status in {Order.PENDING, Order.READY},
            "can_ready": request.user.has_perm("operations.create_order") and order.status == Order.PENDING,
            "can_charge": request.user.has_perm("operations.sell") and order.status in {Order.PENDING, Order.READY},
        },
    )


@require_POST
def order_ready(request, folio):
    require(request.user, "operations.create_order")
    order = get_object_or_404(Order, folio=folio, status=Order.PENDING)
    order.status = Order.READY
    order.save(update_fields=["status"])
    messages.success(request, "Pedido marcado como listo.")
    return redirect("order_detail", folio=folio)


@require_POST
def order_cancel(request, folio):
    require(request.user, "operations.manage_order")
    order = get_object_or_404(Order, folio=folio)
    reason = (request.POST.get("reason") or "").strip()
    if order.status not in {Order.PENDING, Order.READY}:
        messages.error(request, "Este pedido ya no se puede cancelar.")
    elif len(reason) < 3:
        messages.error(request, "El motivo es obligatorio.")
    else:
        order.status = Order.CANCELLED
        order.cancel_reason = reason
        order.save(update_fields=["status", "cancel_reason"])
        messages.success(request, "Pedido cancelado. No hubo movimiento de inventario.")
    return redirect("order_detail", folio=folio)


def order_charge(request, folio):
    require(request.user, "operations.sell")
    config = getattr(request, "business", None) or get_business()
    order = get_object_or_404(Order, folio=folio)
    if order.status not in {Order.PENDING, Order.READY}:
        messages.error(request, "Este pedido ya no se puede cobrar.")
        return redirect("order_detail", folio=folio)
    lines = [{"product_id": line.product_id, "quantity": line.quantity} for line in order.lines.all()]
    if request.method == "POST":
        try:
            sale = confirm_sale(
                user=request.user,
                lines=lines,
                payments=_payments(request.POST),
                shift=current_shift(),
                customer_name=order.customer_name,
                customer_phone=order.customer_phone,
                config=config,
            )
        except CheckoutError as exc:
            messages.error(request, str(exc))
        else:
            order.status = Order.DELIVERED
            order.sale = sale
            order.save(update_fields=["status", "sale"])
            messages.success(request, f"Pedido entregado con la venta {sale.folio}.")
            return redirect("ticket", folio=sale.folio)
    preview = []
    for line in order.lines.select_related("product"):
        preview.append(line)
    return render(request, "operations/order_charge.html", {"order": order, "lines": preview})
