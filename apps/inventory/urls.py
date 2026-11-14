from django.urls import path

from apps.inventory import views

urlpatterns = [
    path("", views.movement_list, name="movement_list"),
    path("movimiento/", views.movement_create, name="movement_create"),
    path("alertas/", views.alerts, name="alerts"),
    path("insumos/", views.supply_list, name="supply_list"),
    path("insumos/nuevo/", views.supply_create, name="supply_create"),
    path("insumos/<int:pk>/", views.supply_detail, name="supply_detail"),
    path("insumos/<int:pk>/editar/", views.supply_edit, name="supply_edit"),
    path("insumos/<int:pk>/movimiento/", views.supply_move, name="supply_move"),
    path("receta/<int:product_id>/", views.recipe_edit, name="recipe_edit"),
]
