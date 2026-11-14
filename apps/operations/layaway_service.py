from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.audit import audit
from apps.core.money import money
from apps.operations.cashbox import CashError, current_shift, record_cash
from apps.operations.checkout import CheckoutError, confirm_sale
from apps.operations.folios import next_folio
from apps.operations.models import Layaway, LayawayAction, LayawayLine, LayawayPayment, StoreCredit
from apps.operations.moneycalc import quote_catalog_line
from apps.operations.stock import available_qty


class LayawayError(Exception):
    pass


def layaway_total(layaway, places=2):
    return money(sum(line.line_total for line in layaway.lines.all()), places)


def layaway_paid(layaway, places=2):
    return money(layaway.payments.aggregate(total=Sum("amount"))["total"] or 0, places)


def layaway_balance(layaway, places=2):
    return money(layaway_total(layaway, places) - layaway_paid(layaway, places), places)


def refresh_expired():
    Layaway.objects.filter(status=Layaway.OPEN, expires_at__lt=timezone.now()).update(status=Layaway.EXPIRED)


def _take_payment(*, layaway, user, method, amount, reference, confirmed, places):
    shift = current_shift()
    value = money(amount, places)
    if value <= 0:
        raise LayawayError("El pago tiene que ser mayor que cero.")
    balance = layaway_balance(layaway, places)
    if value > balance:
        raise LayawayError("El pago no puede ser mayor que el saldo.")
    if method == "card":
        if not confirmed:
            raise LayawayError("Confirma el cobro en la terminal externa antes de registrarlo.")
        digits = (reference or "").replace(" ", "").replace("-", "")
        if digits.isdigit() and len(digits) >= 12:
            raise LayawayError("No guardes el número de tarjeta.")
    elif method == "cash":
        if shift is None:
            raise LayawayError("Abre la caja para recibir efectivo.")
        reference = ""
    else:
        raise LayawayError("Método de pago no válido.")
    payment = LayawayPayment.objects.create(
        layaway=layaway,
        method=method,
        amount=value,
        reference=(reference or "").strip()[:80],
        user=user,
        shift=shift if method == "cash" else None,
    )
    if method == "cash":
        try:
            record_cash(
                shift=shift,
                movement_type="cash_tender",
                amount=value,
                user=user,
                reference=layaway.folio,
                reason=f"Anticipo {layaway.folio}",
            )
        except CashError as exc:
            raise LayawayError(str(exc)) from exc
    return payment


@transaction.atomic
def create_layaway(*, user, lines, customer_name, customer_phone, deposit, method, reference, confirmed, config):
    if not lines:
        raise LayawayError("El apartado no tiene productos.")
    places = config.decimal_places
    name = (customer_name or "").strip()[:120]
    phone = (customer_phone or "").strip()[:20]
    grouped = {}
    for line in lines:
        product_id = int(line["product_id"])
        quantity = int(line["quantity"])
        if quantity < 1:
            raise LayawayError("La cantidad tiene que ser al menos 1.")
        grouped[product_id] = grouped.get(product_id, 0) + quantity
    locked = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=grouped).order_by("pk")
    }
    quoted = []
    for product_id, quantity in grouped.items():
        product = locked.get(product_id)
        if product is None or not product.is_active:
            raise LayawayError("Hay un producto que no se puede apartar.")
        available = available_qty(product)
        if quantity > available:
            raise LayawayError(f"No hay suficientes {product.name} disponibles, contando apartados. Hay {available}.")
        quoted.append(quote_catalog_line(product, quantity, config))
    total = money(sum(row["line_total"] for row in quoted), places)
    deposit = money(deposit, places)
    if deposit <= 0 or deposit >= total:
        raise LayawayError("El anticipo tiene que ser mayor que cero y menor que el total. Si se paga todo, es una venta.")
    layaway = Layaway.objects.create(
        folio=next_folio("A", "layaway"),
        status=Layaway.OPEN,
        customer_name=name,
        customer_phone=phone,
        expires_at=timezone.now() + timedelta(days=config.layaway_default_days),
        policy=config.layaway_policy,
        policy_text=config.policy_text(),
        user=user,
    )
    for row in quoted:
        LayawayLine.objects.create(
            layaway=layaway,
            product=row["product"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            discount=row["discount"],
            line_total=row["line_total"],
        )
    _take_payment(
        layaway=layaway,
        user=user,
        method=method,
        amount=deposit,
        reference=reference,
        confirmed=confirmed,
        places=places,
    )
    return layaway


@transaction.atomic
def add_payment(*, layaway, user, method, amount, reference, confirmed, config):
    layaway = Layaway.objects.select_for_update().get(pk=layaway.pk)
    refresh_expired()
    layaway.refresh_from_db()
    if layaway.status == Layaway.EXPIRED:
        raise LayawayError("El apartado está vencido. El supervisor tiene que extenderlo o cancelarlo.")
    if layaway.status != Layaway.OPEN:
        raise LayawayError("Este apartado ya no recibe pagos.")
    _take_payment(
        layaway=layaway,
        user=user,
        method=method,
        amount=amount,
        reference=reference,
        confirmed=confirmed,
        places=config.decimal_places,
    )
    if layaway_balance(layaway, config.decimal_places) == 0:
        return complete_layaway(layaway=layaway, user=user, config=config)
    return layaway


@transaction.atomic
def complete_layaway(*, layaway, user, config):
    layaway = Layaway.objects.select_for_update().get(pk=layaway.pk)
    if layaway.sale_id:
        return layaway
    if layaway_balance(layaway, config.decimal_places) != 0:
        raise LayawayError("Todavía hay saldo.")
    shift = current_shift()
    lines = [
        {
            "product_id": line.product_id,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "discount": line.discount,
        }
        for line in layaway.lines.all()
    ]
    payments = [
        {"method": payment.method, "tendered": payment.amount, "reference": payment.reference, "confirmed": True}
        for payment in layaway.payments.all()
    ]
    try:
        sale = confirm_sale(
            user=user,
            lines=lines,
            payments=payments,
            shift=shift,
            customer_name=layaway.customer_name,
            customer_phone=layaway.customer_phone,
            price_mode="frozen",
            stock_policy="strict",
            record_cash=False,
            exclude_layaway_id=layaway.pk,
            config=config,
        )
    except CheckoutError as exc:
        raise LayawayError(str(exc)) from exc
    layaway.status = Layaway.COMPLETED
    layaway.sale = sale
    layaway.save(update_fields=["status", "sale"])
    return layaway


@transaction.atomic
def cancel_layaway(*, layaway, user, reason, config):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise LayawayError("El motivo es obligatorio.")
    layaway = Layaway.objects.select_for_update().get(pk=layaway.pk)
    if layaway.status not in {Layaway.OPEN, Layaway.EXPIRED}:
        raise LayawayError("Este apartado ya no se puede cancelar.")
    paid = layaway_paid(layaway, config.decimal_places)
    cash_paid = money(
        sum(payment.amount for payment in layaway.payments.filter(method="cash")),
        config.decimal_places,
    )
    card_paid = money(paid - cash_paid, config.decimal_places)
    detail = layaway.policy_text
    if layaway.policy == "refund" and cash_paid > 0:
        shift = current_shift()
        if shift is None:
            raise LayawayError("Abre la caja para reembolsar el anticipo en efectivo.")
        try:
            record_cash(
                shift=shift,
                movement_type="refund_out",
                amount=cash_paid,
                user=user,
                reference=layaway.folio,
                reason=f"Cancelación {layaway.folio}. {reason}",
            )
        except CashError as exc:
            raise LayawayError(str(exc)) from exc
        detail += f" Se reembolsaron {cash_paid} en efectivo."
    if layaway.policy == "refund" and card_paid > 0:
        detail += f" {card_paid} se cobraron con tarjeta y el reembolso se hace en la terminal, no en esta caja."
    if layaway.policy == "credit" and paid > 0:
        StoreCredit.objects.create(
            customer_name=layaway.customer_name,
            customer_phone=layaway.customer_phone,
            amount=paid,
            remaining=paid,
            origin_label="layaway",
            origin_id=str(layaway.pk),
            user=user,
            note=f"Cancelación {layaway.folio}",
        )
        detail += " El anticipo quedó como saldo a favor."
    if layaway.policy == "retain":
        detail += " El anticipo no se devuelve."
    layaway.status = Layaway.CANCELLED
    layaway.cancel_reason = reason
    layaway.save(update_fields=["status", "cancel_reason"])
    LayawayAction.objects.create(layaway=layaway, action="cancel", reason=reason, user=user, detail=detail)
    audit(user, "layaway.cancel", layaway, f"{reason} {detail}")
    return layaway


@transaction.atomic
def extend_layaway(*, layaway, user, days, reason):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise LayawayError("El motivo es obligatorio.")
    days = int(days)
    if days < 1:
        raise LayawayError("La extensión tiene que ser de al menos un día.")
    layaway = Layaway.objects.select_for_update().get(pk=layaway.pk)
    if layaway.status not in {Layaway.OPEN, Layaway.EXPIRED}:
        raise LayawayError("Este apartado ya no se puede extender.")
    base = layaway.expires_at if layaway.expires_at > timezone.now() else timezone.now()
    layaway.expires_at = base + timedelta(days=days)
    layaway.status = Layaway.OPEN
    layaway.save(update_fields=["expires_at", "status"])
    LayawayAction.objects.create(
        layaway=layaway,
        action="extend",
        reason=reason,
        user=user,
        detail=f"Nueva vigencia {timezone.localtime(layaway.expires_at):%d/%m/%Y %H:%M}.",
    )
    audit(user, "layaway.extend", layaway, reason)
    return layaway
