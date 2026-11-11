from django.urls import NoReverseMatch, reverse


def _add(items, allowed, name, label):
    if not allowed:
        return
    try:
        items.append({"href": reverse(name), "label": label})
    except NoReverseMatch:
        return


def navigation(user, business):
    if not getattr(user, "is_authenticated", False):
        return []
    items = []
    _add(items, True, "dashboard", "Inicio")
    _add(items, user.has_perm("operations.sell"), "pos", "Caja")
    _add(
        items,
        user.has_perm("catalog.consult_products") or user.has_perm("catalog.manage_catalog"),
        "product_list",
        "Productos",
    )
    _add(items, user.has_perm("catalog.manage_promotions"), "promotion_list", "Promociones")
    _add(items, user.has_perm("inventory.view_inventory_history"), "movement_list", "Inventario")
    _add(items, user.has_perm("inventory.view_inventory_history"), "alerts", "Alertas")
    supplies = business and business.supplies_enabled and (
        user.has_perm("inventory.manage_supplies") or user.has_perm("inventory.view_costs")
    )
    _add(items, supplies, "supply_list", "Insumos")
    _add(
        items,
        user.has_perm("operations.view_all_sales") or user.has_perm("operations.sell"),
        "sale_list",
        "Ventas",
    )
    _add(
        items,
        user.has_perm("operations.create_order") or user.has_perm("operations.manage_order"),
        "order_list",
        "Pedidos",
    )
    _add(
        items,
        user.has_perm("operations.create_layaway") or user.has_perm("operations.manage_layaway"),
        "layaway_list",
        "Apartados",
    )
    _add(items, user.has_perm("operations.view_financial_reports"), "report_sales", "Reportes")
    _add(items, user.has_perm("accounts.manage_users"), "user_list", "Usuarios")
    _add(
        items,
        user.has_perm("core.change_global_config") or user.has_perm("core.change_operational_config"),
        "settings_home",
        "Configuración",
    )
    _add(items, user.has_perm("core.view_auditlog"), "audit_list", "Auditoría")
    _add(items, user.has_perm("offline.authorize_device"), "device_list", "Dispositivos")
    _add(items, True, "profile", "Mi cuenta")
    return items
