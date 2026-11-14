from decimal import Decimal

from django.db import transaction

from apps.core.money import money
from apps.inventory.models import StockMovement, Supply, SupplyMovement


class InventoryError(Exception):
    pass


def reserved_units(product_id):
    try:
        from apps.operations.stock import reserved_qty
    except ImportError:
        return 0
    return reserved_qty(product_id)


@transaction.atomic
def apply_stock_change(*, product, quantity_delta, movement_type, reason, user, ref_type="", ref_id=""):
    from apps.catalog.models import Product

    reason = (reason or "").strip()
    if len(reason) < 3:
        raise InventoryError("El motivo es obligatorio.")
    if quantity_delta == 0:
        raise InventoryError("La cantidad no puede ser cero.")
    locked = Product.objects.select_for_update().get(pk=product.pk)
    new_stock = locked.stock + int(quantity_delta)
    if new_stock < 0:
        raise InventoryError("La operación dejaría la existencia en negativo.")
    reserved = reserved_units(locked.pk)
    if new_stock < reserved:
        raise InventoryError(
            f"Hay {reserved} unidades apartadas. La existencia no puede quedar por debajo de esa reserva."
        )
    locked.stock = new_stock
    locked.save(update_fields=["stock", "updated_at"])
    return StockMovement.objects.create(
        product=locked,
        quantity=int(quantity_delta),
        movement_type=movement_type,
        reason=reason,
        user=user,
        ref_type=ref_type,
        ref_id=str(ref_id or ""),
    )


@transaction.atomic
def set_counted_stock(*, product, counted, reason, user):
    from apps.catalog.models import Product

    locked = Product.objects.select_for_update().get(pk=product.pk)
    delta = int(counted) - locked.stock
    if delta == 0:
        return None
    return apply_stock_change(
        product=locked,
        quantity_delta=delta,
        movement_type=StockMovement.ADJUSTMENT,
        reason=reason,
        user=user,
        ref_type="manual",
    )


@transaction.atomic
def set_counted_supply(*, supply, counted, reason, user):
    locked = Supply.objects.select_for_update().get(pk=supply.pk)
    delta = Decimal(counted) - locked.stock
    if delta == 0:
        return None
    return apply_supply_change(
        supply=locked,
        quantity_delta=delta,
        movement_type=SupplyMovement.ADJUSTMENT,
        reason=reason,
        user=user,
    )


@transaction.atomic
def apply_supply_change(*, supply, quantity_delta, movement_type, reason, user):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise InventoryError("El motivo es obligatorio.")
    delta = Decimal(quantity_delta)
    if delta == 0:
        raise InventoryError("La cantidad no puede ser cero.")
    locked = Supply.objects.select_for_update().get(pk=supply.pk)
    new_stock = money(locked.stock + delta, 3)
    if new_stock < 0:
        raise InventoryError("La operación dejaría el insumo en negativo.")
    locked.stock = new_stock
    locked.save(update_fields=["stock", "updated_at"])
    return SupplyMovement.objects.create(
        supply=locked,
        quantity=delta.quantize(Decimal("0.001")),
        movement_type=movement_type,
        reason=reason,
        user=user,
    )
