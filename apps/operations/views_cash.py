from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.access import require
from apps.core.models import get_business
from apps.operations.access import can_close_shift, can_see_shift
from apps.operations.cashbox import (
    CashError,
    close_shift,
    correct_closed_shift,
    current_shift,
    expected_cash,
    manual_movement,
    open_shift,
)
from apps.operations.models import CashShift


def shift_open(request):
    require(request.user, "operations.open_register")
    config = getattr(request, "business", None) or get_business()
    existing = current_shift()
    if request.method == "POST" and existing is None:
        try:
            shift = open_shift(
                user=request.user,
                opening_amount=request.POST.get("opening_amount") or "0",
                currency_code=config.currency_code,
            )
        except CashError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Caja abierta.")
            return redirect("shift_detail", pk=shift.pk)
    return render(
        request,
        "operations/shift_open.html",
        {"existing": existing, "currency": config.currency_code},
    )


def shift_detail(request, pk):
    config = getattr(request, "business", None) or get_business()
    shift = get_object_or_404(CashShift.objects.select_related("opened_by", "closed_by"), pk=pk)
    if not can_see_shift(request.user, shift):
        require(request.user, "operations.view_all_sales")
    movements = shift.movements.select_related("user")
    return render(
        request,
        "operations/shift_detail.html",
        {
            "shift": shift,
            "movements": movements,
            "expected": expected_cash(shift, config.decimal_places) if shift.status == CashShift.OPEN else shift.expected_cash,
            "can_move": shift.status == CashShift.OPEN and request.user.has_perm("operations.manual_cash_movement"),
            "can_close": shift.status == CashShift.OPEN and can_close_shift(request.user, shift),
            "can_correct": shift.status == CashShift.CLOSED and request.user.has_perm("operations.manual_cash_movement"),
        },
    )


@require_http_methods(["GET", "POST"])
def shift_move(request, pk):
    require(request.user, "operations.manual_cash_movement")
    config = getattr(request, "business", None) or get_business()
    shift = get_object_or_404(CashShift, pk=pk, status=CashShift.OPEN)
    if not can_see_shift(request.user, shift):
        require(request.user, "operations.view_all_sales")
    if request.method == "POST":
        try:
            manual_movement(
                shift=shift,
                direction=request.POST.get("direction"),
                amount=request.POST.get("amount"),
                reason=request.POST.get("reason", ""),
                user=request.user,
                places=config.decimal_places,
            )
        except CashError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Movimiento registrado.")
            return redirect("shift_detail", pk=shift.pk)
    return render(request, "operations/shift_move.html", {"shift": shift})


@require_http_methods(["GET", "POST"])
def shift_close(request, pk):
    config = getattr(request, "business", None) or get_business()
    shift = get_object_or_404(CashShift, pk=pk)
    if not can_see_shift(request.user, shift):
        require(request.user, "operations.view_all_sales")
    if shift.status != CashShift.OPEN:
        messages.error(request, "Este cierre ya está confirmado y no se puede modificar.")
        return redirect("shift_detail", pk=shift.pk)
    if not can_close_shift(request.user, shift):
        require(request.user, "operations.close_register")
        messages.error(request, "Solo puedes cerrar la caja que abriste.")
        return redirect("shift_detail", pk=shift.pk)
    if request.method == "POST":
        denoms = request.POST.getlist("denom")
        counts = request.POST.getlist("count")
        try:
            closed = close_shift(
                shift=shift,
                user=request.user,
                counts=list(zip(denoms, counts)),
                places=config.decimal_places,
                note=request.POST.get("note", ""),
            )
        except CashError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Cierre confirmado. Ya no se puede modificar.")
            return redirect("shift_detail", pk=closed.pk)
    return render(
        request,
        "operations/shift_close.html",
        {
            "shift": shift,
            "expected": expected_cash(shift, config.decimal_places),
            "denominations": config.denominations,
        },
    )


@require_http_methods(["POST"])
def shift_correct(request, pk):
    require(request.user, "operations.manual_cash_movement")
    config = getattr(request, "business", None) or get_business()
    shift = get_object_or_404(CashShift, pk=pk, status=CashShift.CLOSED)
    if not can_see_shift(request.user, shift):
        require(request.user, "operations.view_all_sales")
    try:
        correct_closed_shift(
            shift=shift,
            direction=request.POST.get("direction"),
            amount=request.POST.get("amount"),
            reason=request.POST.get("reason", ""),
            user=request.user,
            places=config.decimal_places,
        )
    except CashError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Corrección registrada. El cierre confirmado no cambió.")
    return redirect("shift_detail", pk=shift.pk)
