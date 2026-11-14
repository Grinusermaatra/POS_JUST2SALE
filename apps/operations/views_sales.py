from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.access import require
from apps.operations.access import can_see_sale
from apps.operations.after_sale import (
    AfterSaleError,
    confirm_card_refund,
    create_return,
    returned_qty,
    void_sale,
)
from apps.operations.models import ExternalRefund, Sale


def sale_list(request):
    if request.user.has_perm("operations.view_all_sales"):
        sales = Sale.objects.select_related("user")
    elif request.user.has_perm("operations.sell"):
        sales = Sale.objects.filter(user=request.user)
    else:
        require(request.user, "operations.sell")
        sales = Sale.objects.none()
    folio = (request.GET.get("folio") or "").strip()
    if folio:
        sales = sales.filter(folio__icontains=folio)
    page = Paginator(sales, 30).get_page(request.GET.get("page") or 1)
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "operations/sale_list.html",
        {"page": page, "query": params.urlencode(), "folio": folio, "can_return": request.user.has_perm("operations.create_return")},
    )


def _sale_or_deny(request, folio):
    sale = get_object_or_404(Sale.objects.select_related("user", "shift"), folio=folio)
    if not can_see_sale(request.user, sale):
        require(request.user, "operations.view_all_sales")
    return sale


def sale_detail(request, folio):
    sale = _sale_or_deny(request, folio)
    lines = []
    for line in sale.lines.select_related("product", "promotion"):
        lines.append({"line": line, "returned": returned_qty(line)})
    return render(
        request,
        "operations/sale_detail.html",
        {
            "sale": sale,
            "lines": lines,
            "payments": sale.payments.all(),
            "can_void": request.user.has_perm("operations.void_sale") and sale.status == Sale.CONFIRMED,
            "can_return": request.user.has_perm("operations.create_return") and sale.status == Sale.CONFIRMED,
            "refunds": sale.external_refunds.all(),
            "can_confirm_refund": request.user.has_perm("operations.void_sale")
            or request.user.has_perm("operations.create_return"),
        },
    )


def ticket(request, folio):
    sale = _sale_or_deny(request, folio)
    return render(
        request,
        "operations/ticket.html",
        {"sale": sale, "lines": sale.lines.all(), "payments": sale.payments.all()},
    )


@require_http_methods(["GET", "POST"])
def sale_void(request, folio):
    require(request.user, "operations.void_sale")
    sale = get_object_or_404(Sale, folio=folio)
    if request.method == "POST":
        try:
            void_sale(
                sale=sale,
                user=request.user,
                reason=request.POST.get("reason", ""),
                card_confirmed=request.POST.get("card_confirmed") == "on",
                card_reference=request.POST.get("card_reference", ""),
            )
        except AfterSaleError as exc:
            messages.error(request, str(exc))
        else:
            pending = sale.external_refunds.filter(status=ExternalRefund.PENDING).exists()
            if pending:
                messages.warning(
                    request,
                    f"{sale.folio} anulada. El reembolso de tarjeta sigue pendiente hasta confirmarlo en la terminal externa.",
                )
            else:
                messages.success(request, f"{sale.folio} anulada. La venta sigue en el historial.")
            return redirect("sale_detail", folio=sale.folio)
    return render(
        request,
        "operations/void_form.html",
        {"sale": sale, "card_total": sale.payments.filter(method="card").exists()},
    )


@require_http_methods(["GET", "POST"])
def sale_return(request, folio):
    require(request.user, "operations.create_return")
    config_places = request.business.decimal_places if request.business else 2
    sale = get_object_or_404(Sale, folio=folio, status=Sale.CONFIRMED)
    lines = [{"line": line, "returned": returned_qty(line)} for line in sale.lines.all()]
    if request.method == "POST":
        quantities = {}
        restock = {}
        reasons = {}
        for item in lines:
            key = str(item["line"].pk)
            quantities[key] = request.POST.get(f"qty_{key}") or 0
            restock[key] = request.POST.get(f"restock_{key}") == "on"
            reasons[key] = request.POST.get(f"why_{key}", "")
        try:
            record = create_return(
                sale=sale,
                user=request.user,
                quantities=quantities,
                restock_flags=restock,
                reasons=reasons,
                refund_method=request.POST.get("refund_method"),
                reason=request.POST.get("reason", ""),
                places=config_places,
                card_confirmed=request.POST.get("card_confirmed") == "on",
                card_reference=request.POST.get("card_reference", ""),
            )
        except AfterSaleError as exc:
            messages.error(request, str(exc))
        else:
            if record.refund_status == "pending":
                messages.warning(
                    request,
                    f"Devolución {record.folio} registrada. El reembolso de tarjeta queda pendiente de la terminal externa.",
                )
            else:
                messages.success(request, f"Devolución {record.folio} registrada.")
            return redirect("sale_detail", folio=sale.folio)
    return render(request, "operations/return_form.html", {"sale": sale, "lines": lines})


@require_http_methods(["POST"])
def refund_confirm(request, pk):
    if not (request.user.has_perm("operations.void_sale") or request.user.has_perm("operations.create_return")):
        require(request.user, "operations.create_return")
    refund = get_object_or_404(ExternalRefund, pk=pk)
    if request.POST.get("card_confirmed") != "on":
        messages.error(request, "Confirma que la terminal externa ya hizo el reembolso.")
        return redirect("sale_detail", folio=refund.sale.folio)
    try:
        confirm_card_refund(refund=refund, user=request.user, reference=request.POST.get("card_reference", ""))
    except AfterSaleError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Reembolso de tarjeta confirmado con la referencia de la terminal.")
    return redirect("sale_detail", folio=refund.sale.folio)
