from decimal import Decimal

from apps.catalog.pricing import best_promotion
from apps.core.money import money


def split_tax(net, config):
    places = config.decimal_places
    net = money(net, places)
    rate = Decimal(config.tax_rate) / Decimal("100")
    if rate < 0:
        rate = Decimal("0")
    if config.prices_include_tax or rate == 0:
        if rate == 0:
            tax = money(0, places)
        else:
            tax = money(net - (net / (Decimal("1") + rate)), places)
        subtotal = money(net - tax, places)
        return subtotal, tax, net
    tax = money(net * rate, places)
    return net, tax, money(net + tax, places)


def quote_catalog_line(product, quantity, config, at=None):
    places = config.decimal_places
    promo, unit_discount = best_promotion(product, at=at, places=places)
    gross = money(Decimal(product.price) * quantity, places)
    discount = money(unit_discount * quantity, places)
    if discount > gross:
        discount = gross
    if discount < 0:
        discount = money(0, places)
    net = money(gross - discount, places)
    subtotal, tax, total = split_tax(net, config)
    return {
        "product": product,
        "quantity": quantity,
        "unit_price": money(product.price, places),
        "discount": discount,
        "subtotal": subtotal,
        "tax": tax,
        "line_total": total,
        "promotion": promo,
    }


def quote_frozen_line(product, quantity, unit_price, discount, config):
    places = config.decimal_places
    unit_price = money(unit_price, places)
    gross = money(unit_price * quantity, places)
    discount = money(discount, places)
    if discount < 0 or discount > gross or unit_price <= 0:
        raise ValueError("El precio o el descuento de la partida no es válido.")
    net = money(gross - discount, places)
    subtotal, tax, total = split_tax(net, config)
    return {
        "product": product,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount": discount,
        "subtotal": subtotal,
        "tax": tax,
        "line_total": total,
        "promotion": None,
    }


def settle_payments(total, payments, places):
    cash = money(0, places)
    card = money(0, places)
    rows = []
    for payment in payments:
        method = payment["method"]
        tendered = money(payment["tendered"], places)
        if tendered <= 0:
            raise ValueError("Cada pago tiene que ser mayor que cero.")
        if method == "card":
            if not payment.get("confirmed"):
                raise ValueError("La tarjeta solo queda pagada si confirmas el cobro en la terminal externa.")
            reference = (payment.get("reference") or "").strip()
            digits = reference.replace(" ", "").replace("-", "")
            if digits.isdigit() and len(digits) >= 12:
                raise ValueError("No guardes el número de tarjeta. Escribe solo la referencia de la terminal, si la tienes.")
            card += tendered
        elif method == "cash":
            reference = ""
            cash += tendered
        else:
            raise ValueError("Método de pago no válido.")
        rows.append({"method": method, "amount": tendered, "reference": reference, "confirmed": True})
    if card > total:
        raise ValueError("El pago con tarjeta no puede superar el total. No hay cambio en un pago electrónico.")
    paid = money(cash + card, places)
    if paid < total:
        raise ValueError("El pago no cubre el total. La venta no se confirma.")
    change = money(paid - total, places)
    if change > cash:
        raise ValueError("El cambio solo puede salir del efectivo.")
    return rows, change
