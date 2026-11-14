from django.urls import path

from apps.reports.views import sales_report

urlpatterns = [
    path("", sales_report, name="report_sales"),
]
