from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from apps.core.forms import PosForm


class LoginForm(PosForm):
    username = forms.CharField(label="Usuario")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"


class OtpForm(PosForm):
    token = forms.CharField(label="Código", max_length=16)


class UserCreateForm(PosForm):
    username = forms.CharField(label="Usuario", max_length=150)
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150, required=False)
    email = forms.EmailField(label="Correo", required=False)
    role = forms.ChoiceField(
        label="Rol",
        choices=[("Empleado", "Empleado"), ("Supervisor", "Supervisor"), ("Superadmin", "Superadmin")],
    )
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    is_active = forms.BooleanField(label="Cuenta activa", required=False, initial=True)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Ese usuario ya existe.")
        return username

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


class UserEditForm(PosForm):
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150, required=False)
    email = forms.EmailField(label="Correo", required=False)
    role = forms.ChoiceField(
        label="Rol",
        choices=[("Empleado", "Empleado"), ("Supervisor", "Supervisor"), ("Superadmin", "Superadmin")],
    )
    is_active = forms.BooleanField(label="Cuenta activa", required=False)
    password = forms.CharField(label="Nueva contraseña", required=False, widget=forms.PasswordInput)

    def __init__(self, *args, locked_owner=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.locked_owner = locked_owner
        if locked_owner:
            self.fields["role"].disabled = True
            self.fields["is_active"].disabled = True

    def clean_password(self):
        password = self.cleaned_data.get("password") or ""
        if password:
            validate_password(password)
        return password


class ProfileForm(PosForm):
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150, required=False)
    email = forms.EmailField(label="Correo", required=False)
    current_password = forms.CharField(
        label="Contraseña actual", required=False, widget=forms.PasswordInput
    )
    new_password = forms.CharField(label="Nueva contraseña", required=False, widget=forms.PasswordInput)
    pin = forms.CharField(label="PIN de caja", required=False, widget=forms.PasswordInput)
    pin_confirm = forms.CharField(label="Confirmar PIN", required=False, widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        new_password = cleaned.get("new_password") or ""
        current = cleaned.get("current_password") or ""
        if new_password and not current:
            self.add_error("current_password", "Escribe tu contraseña actual.")
        pin = (cleaned.get("pin") or "").strip()
        confirm = (cleaned.get("pin_confirm") or "").strip()
        if pin or confirm:
            if pin != confirm:
                self.add_error("pin_confirm", "El PIN no coincide.")
            elif not pin.isdigit() or not 4 <= len(pin) <= 6:
                self.add_error("pin", "El PIN debe tener de 4 a 6 dígitos.")
        return cleaned


class DisableOtpForm(PosForm):
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    token = forms.CharField(label="Código actual", max_length=16)
