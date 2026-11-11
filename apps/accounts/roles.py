def role_label(user):
    if not getattr(user, "is_authenticated", False):
        return ""
    if user.is_superuser or user.groups.filter(name="Superadmin").exists():
        return "Superadmin"
    if user.groups.filter(name="Supervisor").exists():
        return "Supervisor"
    if user.groups.filter(name="Empleado").exists():
        return "Empleado"
    return "Sin rol"


def is_employee(user):
    return role_label(user) == "Empleado"


def is_owner_account(user):
    return bool(user.is_superuser)


def can_use_otp(user):
    return role_label(user) in {"Superadmin", "Supervisor"}
