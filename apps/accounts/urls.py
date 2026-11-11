from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("usuarios/", views.user_list, name="user_list"),
    path("usuarios/nuevo/", views.user_create, name="user_create"),
    path("usuarios/<int:pk>/", views.user_edit, name="user_edit"),
    path("usuarios/<int:pk>/eliminar/", views.user_delete, name="user_delete"),
    path("perfil/", views.profile, name="profile"),
    path("seguridad/2fa/", views.otp_status, name="otp_status"),
    path("seguridad/2fa/activar/", views.otp_start, name="otp_start"),
    path("seguridad/2fa/confirmar/", views.otp_confirm, name="otp_confirm"),
    path("seguridad/2fa/qr.png", views.otp_qr, name="otp_qr"),
    path("seguridad/2fa/codigos/", views.otp_codes, name="otp_codes"),
    path("seguridad/2fa/desactivar/", views.otp_disable, name="otp_disable"),
]
