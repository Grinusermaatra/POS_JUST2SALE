from apps.accounts.roles import is_employee


def can_close_shift(user, shift):
    if not user.has_perm("operations.close_register"):
        return False
    if is_employee(user) and shift.opened_by_id != user.id:
        return False
    return True


def can_see_sale(user, sale):
    if user.has_perm("operations.view_all_sales"):
        return True
    return user.has_perm("operations.sell") and sale.user_id == user.id
