from decimal import Decimal

from django.utils import timezone

from apps.core.money import money


def best_promotion(product, at=None, places=2):
    """Elige una sola promoción: la que más descuenta por unidad. No se acumulan."""
    at = at or timezone.now()
    unit = money(product.price, places)
    best = None
    best_amount = money(0, places)
    promos = product.promotions.filter(is_active=True, starts_at__lte=at, ends_at__gte=at).order_by("id")
    for promo in promos:
        if promo.discount_type == promo.PERCENT:
            amount = money(unit * promo.discount_value / Decimal("100"), places)
        else:
            amount = money(promo.discount_value, places)
        if amount > unit:
            amount = unit
        if amount > best_amount:
            best = promo
            best_amount = amount
    return best, best_amount


def price_after_promotion(product, at=None, places=2):
    _, discount = best_promotion(product, at=at, places=places)
    return money(product.price, places) - discount
