from urllib.parse import quote

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import redirect

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("X-Content-Type-Options", "nosniff")
        if settings.PRODUCTION:
            response.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class BusinessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.business = None
        if not request.path.startswith("/static/"):
            try:
                from apps.core.models import get_business

                request.business = get_business()
            except (OperationalError, ProgrammingError):
                request.business = None
        return self.get_response(request)


class LoginRequiredMiddleware:
    EXEMPT = ("/entrar/", "/static/", "/sw.js", "/offline/sincronizar/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated or request.path.startswith(self.EXEMPT):
            return self.get_response(request)
        target = quote(request.get_full_path())
        return redirect(f"{settings.LOGIN_URL}?next={target}")
