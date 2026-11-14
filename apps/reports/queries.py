from datetime import datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.operations.models import ExternalRefund, Payment, ReturnRecord, Sale, SaleLine


def period_bounds(periodo, start_text, end_text):
    today = timezone.localdate()
    if start_text or end_text:
        try:
            start = datetime.strptime(start_text, "%Y-%m-%d").date() if start_text else today
            end = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else today
        except ValueError as exc:
            raise ValueError("La fecha no es válida.") from exc
        if end < start:
            raise ValueError("La fecha final no puede ser anterior a la inicial.")
    elif periodo == "semana":
        start = today - timedelta(days=today.weekday())
        end = today
    elif periodo == "mes":
        start = today.replace(day=1)
        end = today
    else:
        periodo = "dia"
        start = end = today
    start_at = timezone.make_aware(datetime.combine(start, time.min))
    end_at = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
    return periodo or "rango", start, end, start_at, end_at


def report_rows(*, periodo, start_text, end_text, product_id, user_id, method):
    label, start, end, start_at, end_at = period_bounds(periodo, start_text, end_text)
    sales = Sale.objects.filter(status=Sale.CONFIRMED, created_at__gte=start_at, created_at__lt=end_at)
    if user_id:
        sales = sales.filter(user_id=user_id)
    if method in {Payment.CASH, Payment.CARD}:
        sale_ids = sales.filter(payments__method=method).values_list("pk", flat=True).distinct()
        sales = Sale.objects.filter(pk__in=sale_ids)
    sales = sales.select_related("user").order_by("created_at", "id")
    rows = []
    if product_id:
        lines = (
            SaleLine.objects.filter(sale__in=sales, product_id=product_id)
            .select_related("sale", "sale__user", "product")
            .order_by("sale__created_at", "id")
        )
        for line in lines:
            rows.append(
                {
                    "folio": line.sale.folio,
                    "fecha": timezone.localtime(line.sale.created_at),
                    "cajero": line.sale.user.get_username(),
                    "producto": line.name_snapshot,
                    "cantidad": line.quantity,
                    "total": line.line_total,
                    "metodo": method or "",
                }
            )
        total = sum(row["total"] for row in rows)
    else:
        for sale in sales:
            names = {"cash": "Efectivo", "card": "Tarjeta"}
            methods = ", ".join(names.get(item, item) for item in sale.payments.values_list("method", flat=True))
            rows.append(
                {
                    "folio": sale.folio,
                    "fecha": timezone.localtime(sale.created_at),
                    "cajero": sale.user.get_username(),
                    "producto": "",
                    "cantidad": "",
                    "total": sale.total,
                    "metodo": methods,
                }
            )
        total = sales.aggregate(value=Sum("total"))["value"] or 0
    returns = ReturnRecord.objects.filter(created_at__gte=start_at, created_at__lt=end_at).select_related(
        "sale", "user"
    )
    if user_id:
        returns = returns.filter(user_id=user_id)
    if method in {Payment.CASH, Payment.CARD}:
        returns = returns.filter(refund_method=method)
    return_rows = []
    for record in returns.order_by("created_at", "id"):
        return_rows.append(
            {
                "folio": record.folio,
                "venta": record.sale.folio,
                "fecha": timezone.localtime(record.created_at),
                "cajero": record.user.get_username(),
                "total": record.refund_amount,
                "estado": "Pendiente de terminal" if record.refund_status == ReturnRecord.PENDING else "Registrada",
                "metodo": record.refund_method,
            }
        )
    voids = ExternalRefund.objects.filter(
        kind=ExternalRefund.VOID, created_at__gte=start_at, created_at__lt=end_at
    ).select_related("sale", "user")
    if user_id:
        voids = voids.filter(user_id=user_id)
    if method == Payment.CASH:
        voids = voids.none()
    for refund in voids.order_by("created_at", "id"):
        return_rows.append(
            {
                "folio": f"Anulación {refund.sale.folio}",
                "venta": refund.sale.folio,
                "fecha": timezone.localtime(refund.created_at),
                "cajero": refund.user.get_username(),
                "total": refund.amount,
                "estado": "Pendiente de terminal" if refund.status == ExternalRefund.PENDING else "Confirmada en terminal",
                "metodo": "card",
            }
        )
    refunded = returns.filter(refund_status=ReturnRecord.CONFIRMED).aggregate(value=Sum("refund_amount"))["value"] or 0
    pending_returns = returns.filter(refund_status=ReturnRecord.PENDING).aggregate(value=Sum("refund_amount"))["value"] or 0
    pending_voids = voids.filter(status=ExternalRefund.PENDING).aggregate(value=Sum("amount"))["value"] or 0
    confirmed_voids = voids.filter(status=ExternalRefund.CONFIRMED).aggregate(value=Sum("amount"))["value"] or 0
    return {
        "label": label,
        "start": start,
        "end": end,
        "rows": rows,
        "returns": return_rows,
        "total": total,
        "count": len(rows),
        "refunded": refunded + confirmed_voids,
        "pending_refund": pending_returns + pending_voids,
    }
