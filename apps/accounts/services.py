from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Group, User
from django.db.models import Q

from apps.accounts.models import UserProfile

ROLE_NAMES = ("Superadmin", "Supervisor", "Empleado")


def set_role(user, role_name):
    groups = list(Group.objects.filter(name__in=ROLE_NAMES))
    if groups:
        user.groups.remove(*groups)
    user.groups.add(Group.objects.get(name=role_name))


def active_owner_count(exclude_pk=None):
    query = User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(groups__name="Superadmin"))
    if exclude_pk:
        query = query.exclude(pk=exclude_pk)
    return query.distinct().count()


def set_pin(user, pin):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.pin_hash = make_password(pin)
    profile.save(update_fields=["pin_hash"])


def check_pin(user, pin):
    profile = UserProfile.objects.filter(user=user).first()
    if profile is None or not profile.pin_hash:
        return False
    return check_password(pin or "", profile.pin_hash)
