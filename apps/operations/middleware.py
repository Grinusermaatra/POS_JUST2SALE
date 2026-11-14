from datetime import timedelta

from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime

EXEMPT = ("/caja/bloquear/", "/caja/desbloquear/", "/caja/bloqueada/")


class RegisterLockMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated or not request.path.startswith("/caja/"):
            return self.get_response(request)
        if request.path.startswith(EXEMPT):
            return self.get_response(request)
        from apps.accounts.models import UserProfile

        has_pin = UserProfile.objects.filter(user=request.user).exclude(pin_hash="").exists()
        if not has_pin:
            return self.get_response(request)
        business = getattr(request, "business", None)
        minutes = business.inactivity_minutes if business else 5
        locked = bool(request.session.get("register_locked"))
        if not locked:
            seen = parse_datetime(request.session.get("register_seen") or "")
            if seen and timezone.now() - seen > timedelta(minutes=minutes):
                locked = True
                request.session["register_locked"] = True
        if locked:
            if request.method == "GET":
                return redirect("register_lock")
            return HttpResponse("La caja está bloqueada. Desbloquea con el PIN.", status=423)
        request.session["register_seen"] = timezone.now().isoformat()
        return self.get_response(request)
