from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "General"

    def ready(self):
        from django.db.models.signals import post_migrate

        from apps.core.bootstrap import on_post_migrate

        post_migrate.connect(on_post_migrate, dispatch_uid="just2sale-bootstrap")
