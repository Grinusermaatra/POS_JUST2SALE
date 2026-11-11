from django.urls import path

from apps.offline import views

urlpatterns = [
    path("dispositivos/", views.device_list, name="device_list"),
    path("dispositivos/nuevo/", views.device_create, name="device_create"),
    path("dispositivos/<int:pk>/revocar/", views.device_revoke, name="device_revoke"),
    path("catalogo/", views.catalog_api, name="offline_catalog"),
    path("sincronizar/", views.sync_api, name="offline_sync"),
    path("conflictos/", views.conflict_list, name="conflict_list"),
    path("conflictos/<int:pk>/revisar/", views.conflict_resolve, name="conflict_resolve"),
]
