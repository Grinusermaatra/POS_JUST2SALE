from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.catalog.models import Product
from apps.catalog.pricing import best_promotion
from apps.core.money import money
from apps.inventory.models import StockMovement
from apps.operations.cashbox import record_cash as write_cash
from apps.operations.folios import next_folio
from apps.operations.models import Payment, Sale, SaleLine
from apps.operations.moneycalc import quote_catalog_line, quote_frozen_line, settle_payments
from apps.operations.stock import reserved_qty


class CheckoutError(Exception):
    pass


def _as_aware(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _customer(name, phone):
    name = (name or "").strip()[:120]
    phone = (phone or "").strip()[:20]
    if phone and not all(char.isdigit() or char in "+-() " for char in phone):
        raise CheckoutError("El teléfono solo puede tener números, espacios, + y guiones.")
    return name, phone


@transaction.atomic
def confirm_sale(
    *,
    user,
    lines,
    payments,
    shift,
    customer_name="",
    customer_phone="",
    client_uuid=None,
    origin=Sale.ONLINE,
    created_at=None,
    catalog_as_of=None,
    price_mode="catalog",
    stock_policy="strict",
    record_cash=True,
    exclude_layaway_id=None,
    config=None,
):
    if client_uuid:
        existing = Sale.objects.filter(client_uuid=client_uuid).first()
        if existing:
            return existing

    from apps.core.models import get_business

    config = config or get_business()
    places = config.decimal_places
    name, phone = _customer(customer_name, customer_phone)
    if not lines:
        raise CheckoutError("La venta no tiene productos.")

    if shift is not None:
        from apps.operations.models import CashShift

        shift = CashShift.objects.select_for_update().get(pk=shift.pk)

    grouped = defaultdict(lambda: {"quantity": 0, "unit_price": None, "discount": money(0, places)})
    order = []
    for line in lines:
        product_id = int(line["product_id"])
        quantity = int(line["quantity"])
        if quantity < 1:
            raise CheckoutError("La cantidad tiene que ser al menos 1.")
        if product_id not in grouped:
            order.append(product_id)
        bucket = grouped[product_id]
        bucket["quantity"] += quantity
        if price_mode == "frozen":
            unit_price = money(line["unit_price"], places)
            if bucket["unit_price"] is None:
                bucket["unit_price"] = unit_price
            elif bucket["unit_price"] != unit_price:
                raise CheckoutError("No se pueden mezclar precios distintos del mismo producto en una venta.")
            bucket["discount"] = money(bucket["discount"] + money(line.get("discount") or 0, places), places)

    locked = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=order).order_by("pk")
    }
    if len(locked) != len(order):
        raise CheckoutError("Hay un producto que no existe. No se puede cobrar.")

    quoted = []
    conflicts = []
    for product_id in order:
        product = locked[product_id]
        bucket = grouped[product_id]
        if price_mode == "catalog":
            if not product.is_active:
                raise CheckoutError(f"{product.name} no está activo.")
            row = quote_catalog_line(product, bucket["quantity"], config)
            reserved = reserved_qty(product.pk, exclude_layaway_id=exclude_layaway_id)
            available = product.stock - reserved
            if bucket["quantity"] > available:
                raise CheckoutError(f"No hay existencia suficiente de {product.name}. Disponibles: {available}.")
        else:
            try:
                row = quote_frozen_line(
                    product, bucket["quantity"], bucket["unit_price"], bucket["discount"], config
                )
            except ValueError as exc:
                raise CheckoutError(str(exc)) from exc
            if origin == Sale.OFFLINE and money(product.price, places) != row["unit_price"]:
                conflicts.append(
                    {
                        "kind": "price",
                        "product": product,
                        "message": (
                            f"{product.name}: se cobró {row['unit_price']} y el precio actual es {money(product.price, places)}."
                        ),
                    }
                )
            promo, unit_discount = best_promotion(product, places=places)
            allowed = money(unit_discount * row["quantity"], places)
            gross = money(row["unit_price"] * row["quantity"], places)
            if allowed > gross:
                allowed = gross
            if origin == Sale.OFFLINE and row["discount"] > allowed:
                conflicts.append(
                    {
                        "kind": "price",
                        "product": product,
                        "message": (
                            f"{product.name}: el descuento cobrado ({row['discount']}) es mayor que la promoción vigente ({allowed})."
                        ),
                    }
                )
            if stock_policy == "strict":
                reserved = reserved_qty(product.pk, exclude_layaway_id=exclude_layaway_id)
                if bucket["quantity"] > product.stock - reserved:
                    raise CheckoutError(f"No hay existencia suficiente de {product.name}.")
        quoted.append(row)

    subtotal = money(sum(row["subtotal"] for row in quoted), places)
    discount_total = money(sum(row["discount"] for row in quoted), places)
    tax_total = money(sum(row["tax"] for row in quoted), places)
    total = money(sum(row["line_total"] for row in quoted), places)
    if discount_total > money(sum(row["unit_price"] * row["quantity"] for row in quoted), places):
        raise CheckoutError("El descuento no puede ser mayor que la venta.")

    try:
        if total > 0 or payments:
            payment_rows, change = settle_payments(total, payments, places)
        else:
            payment_rows, change = [], money(0, places)
        if total > 0 and not payment_rows:
            raise ValueError("Falta el pago.")
    except ValueError as exc:
        raise CheckoutError(str(exc)) from exc

    if shift is not None and shift.status == shift.OPEN and shift.currency_code != config.currency_code:
        raise CheckoutError("La caja abierta está en otra moneda. Ciérrala antes de cobrar.")
    if shift is None or shift.status != shift.OPEN:
        if record_cash and stock_policy == "strict":
            raise CheckoutError("Abre la caja antes de cobrar.")
        if record_cash and any(row["method"] == "cash" for row in payment_rows):
            conflicts.append(
                {"kind": "cash", "product": None, "message": "La venta en efectivo llegó sin una caja abierta. No se alteró un cierre."}
            )
        record_cash = False
        shift = None

    moment = _as_aware(created_at) or timezone.now()
    if origin == Sale.OFFLINE:
        oldest = timezone.now() - timedelta(days=config.offline_auth_days)
        newest = timezone.now() + timedelta(hours=1)
        if moment < oldest or moment > newest:
            conflicts.append(
                {
                    "kind": "other",
                    "product": None,
                    "message": "La hora del dispositivo quedó fuera del periodo autorizado. Se usó la hora del servidor.",
                }
            )
            moment = timezone.now()

    sync_status = Sale.SYNC_ONLINE if origin == Sale.ONLINE else Sale.SYNC_SYNCED
    sale = Sale.objects.create(
        folio=next_folio("V", "sale"),
        client_uuid=client_uuid,
        user=user,
        created_at=moment,
        currency_code=config.currency_code,
        status=Sale.CONFIRMED,
        origin=origin,
        sync_status=sync_status,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total=total,
        change_given=change,
        shift=shift if shift and shift.status == shift.OPEN else None,
        customer_name=name,
        customer_phone=phone,
        catalog_as_of=_as_aware(catalog_as_of),
    )

    for row in quoted:
        product = row["product"]
        SaleLine.objects.create(
            sale=sale,
            product=product,
            name_snapshot=product.name,
            code_snapshot=product.code,
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            discount=row["discount"],
            tax=row["tax"],
            line_total=row["line_total"],
            promotion=row["promotion"],
        )
        if stock_policy == "strict":
            applied = row["quantity"]
        else:
            applied = min(row["quantity"], product.stock)
            if applied < row["quantity"]:
                conflicts.append(
                    {
                        "kind": "stock",
                        "product": product,
                        "message": (
                            f"{product.name}: la venta pidió {row['quantity']} y solo se descontaron {applied}. "
                            "La existencia no quedó negativa."
                        ),
                    }
                )
        if applied:
            product.stock -= applied
            product.save(update_fields=["stock", "updated_at"])
            StockMovement.objects.create(
                product=product,
                quantity=-applied,
                movement_type=StockMovement.SALE,
                reason=f"Venta {sale.folio}",
                user=user,
                ref_type="sale",
                ref_id=str(sale.pk),
            )
        reserved_after = reserved_qty(product.pk, exclude_layaway_id=exclude_layaway_id)
        if product.stock < reserved_after:
            conflicts.append(
                {
                    "kind": "stock",
                    "product": product,
                    "message": f"{product.name}: la existencia quedó por debajo de lo apartado. Requiere revisión.",
                }
            )

    for row in payment_rows:
        Payment.objects.create(sale=sale, **row)
    if record_cash and sale.shift_id and change >= 0:
        for row in payment_rows:
            if row["method"] == "cash":
                write_cash(
                    shift=sale.shift,
                    movement_type="cash_tender",
                    amount=row["amount"],
                    user=user,
                    reference=sale.folio,
                    reason=f"Venta {sale.folio}",
                )
        if change > 0:
            write_cash(
                shift=sale.shift,
                movement_type="change_out",
                amount=change,
                user=user,
                reference=sale.folio,
                reason=f"Cambio {sale.folio}",
            )

    if conflicts:
        from apps.offline.models import SyncConflict

        notes = []
        for conflict in conflicts:
            SyncConflict.objects.create(
                kind=conflict["kind"],
                sale=sale,
                product=conflict["product"],
                message=conflict["message"],
            )
            notes.append(conflict["message"])
            if conflict["kind"] in {"stock", "cash"}:
                sale.sync_status = Sale.SYNC_ERROR
        sale.sync_note = " ".join(notes)
        sale.save(update_fields=["sync_status", "sync_note"])
    return sale
