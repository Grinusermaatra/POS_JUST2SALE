from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    pin_hash = models.CharField(max_length=128, blank=True)

    class Meta:
        permissions = [
            ("manage_users", "Crear, editar o eliminar usuarios"),
            ("assign_roles", "Asignar roles"),
        ]

    def __str__(self):
        return self.user.get_username()
