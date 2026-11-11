from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.audit import audit
from apps.core.money import money
from apps.operations.models import CashMovement, CashShift


class CashError(Exception):
    pass


def current_shift():
    return CashShift.objects.filter(status=CashShift.OPEN).select_related("opened_by").first()


def expected_cash(shift, places=2):
    total = money(shift.opening_amount, places)
    for movement in shift.movements.filter(affects_expected=True):
        if movement.movement_type in {CashMovement.TENDER, CashMovement.MANUAL_IN}:
            total += movement.amount
        else:
            total -= movement.amount
    return money(total, places)


@transaction.atomic
def open_shift(*, user, opening_amount, currency_code, client_uuid=None, opened_at=None):
    if client_uuid:
        existing = CashShift.objects.filter(client_uuid=client_uuid).first()
        if existing:
            return existing
    if CashShift.objects.filter(status=CashShift.OPEN).exists():
        raise CashError("Ya hay una caja abierta. Ciérrala antes de abrir otra.")
    amount = money(opening_amount, 2)
    if amount < 0:
        raise CashError("El fondo inicial no puede ser negativo.")
    return CashShift.objects.create(
        client_uuid=client_uuid,
        opened_by=user,
        opened_at=opened_at or timezone.now(),
        currency_code=currency_code,
        opening_amount=amount,
        status=CashShift.OPEN,
    )


def record_cash(*, shift, movement_type, amount, user, reference="", reason="", client_uuid=None, affects_expected=True):
    if client_uuid:
        existing = CashMovement.objects.filter(client_uuid=client_uuid).first()
        if existing:
            return existing
    shift = CashShift.objects.select_for_update().get(pk=shift.pk)
    value = money(amount, 2)
    if value <= 0:
        raise CashError("El importe tiene que ser mayor que cero.")
    if shift.status != CashShift.OPEN and affects_expected:
        raise CashError("La caja ya está cerrada. El cierre no se modifica.")
    return CashMovement.objects.create(
        shift=shift,
        client_uuid=client_uuid,
        movement_type=movement_type,
        amount=value,
        affects_expected=affects_expected,
        user=user,
        currency_code=shift.currency_code,
        reference=reference,
        reason=(reason or "").strip(),
    )


@transaction.atomic
def manual_movement(*, shift, direction, amount, reason, user, places=2):
    if shift.status != CashShift.OPEN:
        raise CashError("Solo se registran entradas y retiros con la caja abierta.")
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise CashError("El motivo es obligatorio.")
    value = money(amount, places)
    if direction == "out" and value > expected_cash(shift, places):
        raise CashError("El retiro dejaría el efectivo esperado en negativo.")
    movement_type = CashMovement.MANUAL_IN if direction == "in" else CashMovement.MANUAL_OUT
    movement = record_cash(shift=shift, movement_type=movement_type, amount=value, user=user, reason=reason)
    audit(user, "cash.movement", shift, f"{movement.get_movement_type_display()} {value}. {reason}")
    return movement


@transaction.atomic
def close_shift(*, shift, user, counts, places=2, note=""):
    locked = CashShift.objects.select_for_update().get(pk=shift.pk)
    if locked.status != CashShift.OPEN:
        raise CashError("Este cierre ya está confirmado y no se puede modificar.")
    expected = expected_cash(locked, places)
    counted = money(0, places)
    stored = {}
    for raw_denom, raw_count in counts:
        denom = money(raw_denom, places)
        if denom <= 0:
            raise CashError("Hay una denominación inválida.")
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError) as exc:
            raise CashError("El conteo tiene que ser un número entero.") from exc
        if count < 0:
            raise CashError("El conteo no puede ser negativo.")
        counted += money(denom * Decimal(count), places)
        stored[f"{denom:.{places}f}"] = count
    difference = money(counted - expected, places)
    locked.status = CashShift.CLOSED
    locked.closed_by = user
    locked.closed_at = timezone.now()
    locked.expected_cash = expected
    locked.counted_cash = counted
    locked.difference = difference
    locked.denominations = stored
    locked.note = (note or "").strip()[:200]
    locked.save()
    audit(
        user,
        "cash.close",
        locked,
        f"Esperado {expected}. Contado {counted}. Diferencia {difference}.",
    )
    return locked


@transaction.atomic
def correct_closed_shift(*, shift, direction, amount, reason, user, places=2):
    locked = CashShift.objects.select_for_update().get(pk=shift.pk)
    if locked.status != CashShift.CLOSED:
        raise CashError("La corrección auditada es para un cierre ya confirmado.")
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise CashError("El motivo es obligatorio.")
    value = money(amount, places)
    movement = record_cash(
        shift=locked,
        movement_type=CashMovement.ADJUSTMENT,
        amount=value,
        user=user,
        reason=f"{'Entrada' if direction == 'in' else 'Salida'}: {reason}",
        affects_expected=False,
    )
    audit(user, "cash.adjustment", locked, f"Corrección {value} ({direction}). {reason}")
    return movement
