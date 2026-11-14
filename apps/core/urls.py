from django.urls import path

from apps.core import views

urlpatterns = [
    path("", views.settings_home, name="settings_home"),
    path("negocio/", views.settings_global, name="settings_global"),
    path("operacion/", views.settings_operational, name="settings_operational"),
    path("integraciones/", views.integrations, name="integrations"),
    path("auditoria/", views.audit_list, name="audit_list"),
]
