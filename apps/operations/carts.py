def _read(request, key):
    return [dict(line) for line in request.session.get(key, [])]


def _write(request, key, lines):
    request.session[key] = lines
    request.session.modified = True


def add_line(lines, product_id, quantity):
    quantity = int(quantity)
    if quantity < 1:
        return lines
    for line in lines:
        if line["product_id"] == product_id:
            line["quantity"] += quantity
            return lines
    lines.append({"product_id": product_id, "quantity": quantity})
    return lines


def set_qty(lines, product_id, quantity):
    quantity = int(quantity)
    kept = []
    for line in lines:
        if line["product_id"] != product_id:
            kept.append(line)
        elif quantity > 0:
            kept.append({"product_id": product_id, "quantity": quantity})
    return kept
