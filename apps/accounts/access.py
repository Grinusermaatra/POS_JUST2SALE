from django.core.exceptions import PermissionDenied


def require(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied("No tienes permiso para esta acción.")
