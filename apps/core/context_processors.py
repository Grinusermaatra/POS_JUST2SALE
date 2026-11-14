from django.urls import NoReverseMatch

from apps.accounts.roles import role_label
from apps.core.navigation import navigation


def pos_context(request):
    user = getattr(request, "user", None)
    business = getattr(request, "business", None)
    locked = False
    if hasattr(request, "session"):
        locked = bool(request.session.get("register_locked"))
    try:
        nav = navigation(user, business) if user is not None else []
    except NoReverseMatch:
        nav = []
    return {
        "business": business,
        "role_label": role_label(user) if user is not None else "",
        "register_locked": locked,
        "nav": nav,
    }
