from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.audit import audit
from apps.core.money import money
from apps.inventory.models import StockMovement
from apps.operations.cashbox import CashError, current_shift, record_cash
from apps.operations.folios import next_folio
from apps.operations.models import Payment, ReturnLine, ReturnRecord, Sale, SaleLine, StoreCredit


class AfterSaleError(Exception):
    pass


def returned_qty(sale_line):
    return sale_line.return_lines.aggregate(total=Sum("quantity"))["total"] or 0


def _cash_shift_for_reversal(sale):
    if sale.shift_id and sale.shift.status == sale.shift.OPEN:
        return sale.shift
    shift = current_shift()
    if shift is None:
        raise AfterSaleError("Abre la caja para registrar el efectivo de esta operación. El cierre anterior no se modifica.")
    return shift


@transaction.atomic
def void_sale(*, sale, user, reason):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise AfterSaleError("El motivo es obligatorio.")
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status == Sale.VOIDED:
        raise AfterSaleError("Esta venta ya está anulada.")
    if sale.returns.exists():
        raise AfterSaleError("Esta venta ya tiene devoluciones. Registra otra devolución por lo que reste.")
    for line in sale.lines.select_related("product"):
        product = line.product.__class__.objects.select_for_update().get(pk=line.product_id)
        product.stock += line.quantity
        product.save(update_fields=["stock", "updated_at"])
        StockMovement.objects.create(
            product=product,
            quantity=line.quantity,
            movement_type=StockMovement.VOID_IN,
            reason=f"Anulación {sale.folio}. {reason}",
            user=user,
            ref_type="sale",
            ref_id=str(sale.pk),
        )
    cash_in = money(
        sum(payment.amount for payment in sale.payments.filter(method=Payment.CASH)),
        2,
    )
    net_cash = money(cash_in - sale.change_given, 2)
    if net_cash > 0:
        shift = _cash_shift_for_reversal(sale)
        record_cash(
            shift=shift,
            movement_type="refund_out",
            amount=net_cash,
            user=user,
            reference=sale.folio,
            reason=f"Anulación {sale.folio}. {reason}",
        )
    sale.status = Sale.VOIDED
    sale.save(update_fields=["status"])
    audit(user, "sale.void", sale, reason)
    return sale


@transaction.atomic
def create_return(*, sale, user, quantities, restock_flags, reasons, refund_method, reason, places=2):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise AfterSaleError("El motivo es obligatorio.")
    if refund_method not in {"cash", "card", "credit"}:
        raise AfterSaleError("Elige efectivo, tarjeta o saldo a favor.")
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.CONFIRMED:
        raise AfterSaleError("No se puede devolver una venta anulada.")
    chosen = []
    refund = money(0, places)
    for line in sale.lines.select_related("product"):
        qty = int(quantities.get(str(line.pk), quantities.get(line.pk, 0)) or 0)
        if qty < 0:
            raise AfterSaleError("La cantidad no puede ser negativa.")
        if qty == 0:
            continue
        already = returned_qty(line)
        if qty + already > line.quantity:
            raise AfterSaleError(f"No puedes devolver más {line.name_snapshot} del que se vendió.")
        restock = bool(restock_flags.get(str(line.pk), restock_flags.get(line.pk, True)))
        note = (reasons.get(str(line.pk), reasons.get(line.pk, "")) or "").strip()
        if not restock and len(note) < 3:
            raise AfterSaleError(f"Indica por qué {line.name_snapshot} no vuelve al inventario.")
        share = money(Decimal(line.line_total) * Decimal(qty) / Decimal(line.quantity), places)
        refund += share
        chosen.append((line, qty, restock, note, share))
    if not chosen:
        raise AfterSaleError("Indica qué se devuelve.")
    refund = money(refund, places)
    record = ReturnRecord.objects.create(
        folio=next_folio("D", "return"),
        sale=sale,
        user=user,
        created_at=timezone.now(),
        reason=reason,
        refund_method=refund_method,
        refund_amount=refund,
    )
    for line, qty, restock, note, share in chosen:
        ReturnLine.objects.create(
            return_record=record,
            sale_line=line,
            quantity=qty,
            restock=restock,
            no_restock_reason="" if restock else note,
        )
        if restock:
            product = line.product.__class__.objects.select_for_update().get(pk=line.product_id)
            product.stock += qty
            product.save(update_fields=["stock", "updated_at"])
            StockMovement.objects.create(
                product=product,
                quantity=qty,
                movement_type=StockMovement.RETURN_IN,
                reason=f"Devolución {record.folio}. {reason}",
                user=user,
                ref_type="return",
                ref_id=str(record.pk),
            )
    if refund > 0 and refund_method == "cash":
        shift = _cash_shift_for_reversal(sale)
        try:
            record_cash(
                shift=shift,
                movement_type="refund_out",
                amount=refund,
                user=user,
                reference=record.folio,
                reason=f"Devolución {record.folio}. {reason}",
            )
        except CashError as exc:
            raise AfterSaleError(str(exc)) from exc
    if refund > 0 and refund_method == "credit":
        StoreCredit.objects.create(
            customer_name=sale.customer_name,
            customer_phone=sale.customer_phone,
            amount=refund,
            remaining=refund,
            origin_label="return",
            origin_id=str(record.pk),
            user=user,
            note=f"Devolución {record.folio}",
        )
    audit(user, "sale.return", record, f"{record.folio} de {sale.folio}. {reason}")
    return record
