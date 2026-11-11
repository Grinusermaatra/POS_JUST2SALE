from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Cuentas"

    def ready(self):
        from django.contrib.auth.models import User
        from django.db.models.signals import post_save

        from apps.accounts.signals import create_profile

        post_save.connect(create_profile, sender=User, dispatch_uid="just2sale-profile")
