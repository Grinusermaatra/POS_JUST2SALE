from django.db.models import Sum

from apps.operations.models import Layaway


def reserved_qty(product_id, exclude_layaway_id=None):
    from apps.operations.models import LayawayLine

    query = LayawayLine.objects.filter(
        product_id=product_id,
        layaway__status__in=[Layaway.OPEN, Layaway.EXPIRED],
    )
    if exclude_layaway_id:
        query = query.exclude(layaway_id=exclude_layaway_id)
    return query.aggregate(total=Sum("quantity"))["total"] or 0


def available_qty(product, exclude_layaway_id=None):
    return product.stock - reserved_qty(product.pk, exclude_layaway_id)
