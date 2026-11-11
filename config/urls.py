from django.urls import include, path

from apps.accounts import views as account_views
from apps.core.views import dashboard
from apps.offline.views import service_worker

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("entrar/", account_views.login_view, name="login"),
    path("entrar/otp/", account_views.otp_view, name="otp"),
    path("salir/", account_views.logout_view, name="logout"),
    path("sw.js", service_worker, name="service_worker"),
    path("", include("apps.accounts.urls")),
    path("configuracion/", include("apps.core.urls")),
    path("productos/", include("apps.catalog.urls")),
    path("inventario/", include("apps.inventory.urls")),
    path("caja/", include("apps.operations.urls")),
    path("offline/", include("apps.offline.urls")),
]

handler403 = "apps.core.errors.forbidden"
handler404 = "apps.core.errors.not_found"
handler500 = "apps.core.errors.server_error"
