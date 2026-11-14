def audit(user, action, obj=None, detail="", extra=None):
    from apps.core.models import AuditLog

    username = ""
    actor = None
    if getattr(user, "is_authenticated", False):
        actor = user
        username = user.get_username()
    AuditLog.objects.create(
        user=actor,
        username_snapshot=username,
        action=action,
        object_label=obj.__class__.__name__ if obj is not None else "",
        object_id="" if obj is None or obj.pk is None else str(obj.pk),
        detail=detail,
        extra=extra or {},
    )
