from django.urls import include, path

from apps.accounts import views as account_views
from apps.core.views import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("entrar/", account_views.login_view, name="login"),
    path("entrar/otp/", account_views.otp_view, name="otp"),
    path("salir/", account_views.logout_view, name="logout"),
    path("", include("apps.accounts.urls")),
    path("configuracion/", include("apps.core.urls")),
    path("productos/", include("apps.catalog.urls")),
    path("inventario/", include("apps.inventory.urls")),
]

handler403 = "apps.core.errors.forbidden"
handler404 = "apps.core.errors.not_found"
handler500 = "apps.core.errors.server_error"
