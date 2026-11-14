from django.contrib.auth.models import Group, Permission, User

ROLE_NAMES = ("Superadmin", "Supervisor", "Empleado")

ALL_PERMISSIONS = [
    "accounts.manage_users",
    "accounts.assign_roles",
    "core.change_global_config",
    "core.change_operational_config",
    "core.manage_integrations",
    "core.toggle_modules",
    "core.view_auditlog",
    "catalog.consult_products",
    "catalog.manage_catalog",
    "catalog.manage_promotions",
    "inventory.adjust_inventory",
    "inventory.view_inventory_history",
    "inventory.manage_supplies",
    "inventory.view_costs",
    "operations.sell",
    "operations.void_sale",
    "operations.view_all_sales",
    "operations.create_return",
    "operations.open_register",
    "operations.close_register",
    "operations.manual_cash_movement",
    "operations.create_order",
    "operations.manage_order",
    "operations.create_layaway",
    "operations.manage_layaway",
    "operations.view_financial_reports",
    "offline.authorize_device",
]

SUPERVISOR_PERMISSIONS = [
    "core.change_operational_config",
    "core.view_auditlog",
    "catalog.consult_products",
    "catalog.manage_catalog",
    "catalog.manage_promotions",
    "inventory.adjust_inventory",
    "inventory.view_inventory_history",
    "inventory.manage_supplies",
    "inventory.view_costs",
    "operations.sell",
    "operations.void_sale",
    "operations.view_all_sales",
    "operations.create_return",
    "operations.open_register",
    "operations.close_register",
    "operations.manual_cash_movement",
    "operations.create_order",
    "operations.manage_order",
    "operations.create_layaway",
    "operations.manage_layaway",
    "operations.view_financial_reports",
]

EMPLOYEE_PERMISSIONS = [
    "catalog.consult_products",
    "operations.sell",
    "operations.create_order",
    "operations.create_layaway",
]

REGISTER_PERMISSIONS = [
    "operations.open_register",
    "operations.close_register",
]


def _existing(labels):
    found = []
    for label in labels:
        app_label, codename = label.split(".")
        perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
        if perm:
            found.append(perm)
    return found


def sync_roles(employee_register=None):
    from apps.core.models import BusinessConfig

    if employee_register is None:
        config = BusinessConfig.objects.filter(pk=1).first()
        employee_register = bool(config and config.cashiers_may_open_register)

    employee = list(EMPLOYEE_PERMISSIONS)
    if employee_register:
        employee.extend(REGISTER_PERMISSIONS)

    mapping = {
        "Superadmin": ALL_PERMISSIONS,
        "Supervisor": SUPERVISOR_PERMISSIONS,
        "Empleado": employee,
    }
    for name, labels in mapping.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set(_existing(labels))

    superadmin = Group.objects.get(name="Superadmin")
    for user in User.objects.filter(is_superuser=True):
        user.groups.add(superadmin)

    for user in User.objects.all():
        from apps.accounts.models import UserProfile

        UserProfile.objects.get_or_create(user=user)


def ensure_config():
    from apps.core.models import get_business

    get_business()


def on_post_migrate(sender, **kwargs):
    from django.db import connection

    tables = set(connection.introspection.table_names())
    if "core_businessconfig" not in tables or "auth_permission" not in tables:
        return
    ensure_config()
    if "auth_group" not in tables or "accounts_userprofile" not in tables:
        return
    sync_roles()
