from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def money(value, places=2):
    if value is None or value == "":
        raise ValueError("Importe vacío.")
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(" ", "")
        if cleaned.count(",") == 1 and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        value = cleaned
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Importe inválido.") from exc
    if places < 0:
        places = 0
    quantum = Decimal("1").scaleb(-places)
    return amount.quantize(quantum, rounding=ROUND_HALF_UP)


def money_or_none(value, places=2):
    if value is None or str(value).strip() == "":
        return None
    return money(value, places)
