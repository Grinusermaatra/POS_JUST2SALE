from django.urls import path

from apps.catalog import views

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("nuevo/", views.product_create, name="product_create"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
    path("<int:pk>/editar/", views.product_edit, name="product_edit"),
    path("<int:pk>/qr.png", views.product_qr, name="product_qr"),
    path("<int:pk>/barras.png", views.product_barcode, name="product_barcode"),
    path("<int:pk>/imprimir/", views.product_print, name="product_print"),
    path("<int:pk>/componentes/", views.package_add, name="package_add"),
    path("<int:pk>/componentes/<int:component_id>/quitar/", views.package_remove, name="package_remove"),
    path("promociones/", views.promotion_list, name="promotion_list"),
    path("promociones/nueva/", views.promotion_create, name="promotion_create"),
    path("promociones/<int:pk>/", views.promotion_edit, name="promotion_edit"),
]
