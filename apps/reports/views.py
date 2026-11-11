import csv
from io import BytesIO

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import render
from openpyxl import Workbook

from apps.accounts.access import require
from apps.catalog.models import Product
from apps.core.audit import audit
from apps.reports.queries import report_rows

COLUMNS = ["Folio", "Fecha", "Cajero", "Producto", "Cantidad", "Total", "Método"]


def _filters(request):
    return {
        "periodo": request.GET.get("periodo") or "dia",
        "start_text": (request.GET.get("desde") or "").strip(),
        "end_text": (request.GET.get("hasta") or "").strip(),
        "product_id": request.GET.get("producto") if (request.GET.get("producto") or "").isdigit() else "",
        "user_id": request.GET.get("usuario") if (request.GET.get("usuario") or "").isdigit() else "",
        "method": request.GET.get("metodo") or "",
    }


def _build(request):
    filters = _filters(request)
    data = report_rows(
        periodo=filters["periodo"],
        start_text=filters["start_text"],
        end_text=filters["end_text"],
        product_id=int(filters["product_id"]) if filters["product_id"] else None,
        user_id=int(filters["user_id"]) if filters["user_id"] else None,
        method=filters["method"],
    )
    return filters, data


def _table(data):
    table = []
    for row in data["rows"]:
        table.append(
            [
                row["folio"],
                row["fecha"].strftime("%d/%m/%Y %H:%M"),
                row["cajero"],
                row["producto"],
                row["cantidad"],
                f"{row['total']:.2f}",
                row["metodo"],
            ]
        )
    return table


def sales_report(request):
    require(request.user, "operations.view_financial_reports")
    try:
        filters, data = _build(request)
    except ValueError as exc:
        filters, data = _filters(request), None
        return render(
            request,
            "reports/sales.html",
            {
                "error": str(exc),
                "filters": filters,
                "products": Product.objects.order_by("name"),
                "users": User.objects.order_by("username"),
            },
        )
    export = request.GET.get("exportar")
    detail = (
        f"periodo {data['start']} a {data['end']}; producto {filters['product_id'] or 'todos'}; "
        f"usuario {filters['user_id'] or 'todos'}; metodo {filters['method'] or 'todos'}"
    )
    if export in {"csv", "xlsx"}:
        audit(request.user, "report.export", detail=f"{export}. {detail}")
        if export == "csv":
            return _csv(data)
        return _xlsx(data)
    audit(request.user, "report.view", detail=detail)
    query = request.GET.copy()
    query.pop("exportar", None)
    return render(
        request,
        "reports/sales.html",
        {
            "filters": filters,
            "data": data,
            "products": Product.objects.order_by("name"),
            "users": User.objects.order_by("username"),
            "query": query.urlencode(),
        },
    )


def _csv(data):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ventas.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(COLUMNS)
    writer.writerows(_table(data))
    return response


def _xlsx(data):
    book = Workbook()
    sheet = book.active
    sheet.title = "Ventas"
    sheet.append(COLUMNS)
    for row in _table(data):
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="ventas.xlsx"'
    return response
