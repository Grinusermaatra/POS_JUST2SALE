from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.access import require
from apps.accounts.forms import DisableOtpForm, LoginForm, OtpForm, ProfileForm, UserCreateForm, UserEditForm
from apps.accounts.roles import can_use_otp, is_owner_account, role_label
from apps.accounts.services import active_owner_count, set_pin, set_role
from apps.accounts.throttle import lock_message, register_failure, register_success
from apps.core.audit import audit
from apps.core.models import get_business

PRE_2FA = "pre_2fa_user_id"


def _next_url(request):
    target = request.POST.get("next") or request.GET.get("next") or "/"
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return "/"


def _needs_otp(user):
    if not can_use_otp(user):
        return False
    from django_otp.plugins.otp_totp.models import TOTPDevice

    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def _otp_ok(user, token):
    from django_otp.plugins.otp_static.models import StaticDevice
    from django_otp.plugins.otp_totp.models import TOTPDevice

    cleaned = (token or "").strip().replace(" ", "")
    for device in TOTPDevice.objects.filter(user=user, confirmed=True):
        if device.verify_token(cleaned):
            return True
    for device in StaticDevice.objects.filter(user=user, confirmed=True):
        if device.verify_token(cleaned):
            return True
    return False


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"].strip()
        blocked = lock_message(request, username)
        if blocked:
            form.add_error(None, blocked)
        else:
            user = authenticate(request, username=username, password=form.cleaned_data["password"])
            if user is None:
                register_failure(request, username)
                blocked = lock_message(request, username)
                form.add_error(None, blocked or "Usuario o contraseña incorrectos.")
            elif _needs_otp(user):
                request.session[PRE_2FA] = user.pk
                request.session["pre_2fa_next"] = _next_url(request)
                return redirect("otp")
            else:
                register_success(request, username)
                login(request, user)
                return redirect(_next_url(request))
    return render(request, "login.html", {"form": form, "next": request.GET.get("next", "")})


@never_cache
def otp_view(request):
    user_id = request.session.get(PRE_2FA)
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if user is None:
        return redirect("login")
    form = OtpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        blocked = lock_message(request, user.get_username())
        if blocked:
            form.add_error(None, blocked)
        elif _otp_ok(user, form.cleaned_data["token"]):
            register_success(request, user.get_username())
            target = request.session.pop("pre_2fa_next", "/")
            request.session.pop(PRE_2FA, None)
            login(request, user)
            return redirect(target or "/")
        else:
            register_failure(request, user.get_username())
            form.add_error("token", lock_message(request, user.get_username()) or "Código incorrecto.")
    return render(request, "otp.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


def user_list(request):
    require(request.user, "accounts.manage_users")
    users = User.objects.order_by("username").prefetch_related("groups")
    rows = [{"user": item, "role": role_label(item)} for item in users]
    return render(request, "accounts/user_list.html", {"rows": rows})


def user_create(request):
    require(request.user, "accounts.manage_users")
    require(request.user, "accounts.assign_roles")
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                user = User(
                    username=data["username"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    email=data["email"],
                    is_active=data["is_active"],
                )
                validate_password(data["password"], user)
                user.set_password(data["password"])
                user.save()
                set_role(user, data["role"])
                audit(request.user, "permission.change", user, f"Alta de usuario con rol {data['role']}.")
        except ValidationError as exc:
            form.add_error("password", " ".join(exc.messages))
        except IntegrityError:
            form.add_error("username", "Ese usuario ya existe.")
        else:
            messages.success(request, "Usuario creado.")
            return redirect("user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Nuevo usuario", "editing": None})


def user_edit(request, pk):
    require(request.user, "accounts.manage_users")
    require(request.user, "accounts.assign_roles")
    user = get_object_or_404(User, pk=pk)
    locked = is_owner_account(user)
    initial = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": role_label(user) if role_label(user) in {"Empleado", "Supervisor", "Superadmin"} else "Empleado",
        "is_active": user.is_active,
    }
    form = UserEditForm(request.POST or None, initial=initial, locked_owner=locked)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        new_role = role_label(user) if locked else data["role"]
        new_active = user.is_active if locked else data["is_active"]
        leaving_owner = role_label(user) == "Superadmin" and (new_role != "Superadmin" or not new_active)
        if leaving_owner and active_owner_count(exclude_pk=user.pk) == 0:
            form.add_error(None, "Tiene que quedar al menos un Superadmin activo.")
        else:
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.email = data["email"]
            user.is_active = new_active
            if data["password"]:
                user.set_password(data["password"])
            user.save()
            if not locked:
                set_role(user, new_role)
            audit(request.user, "permission.change", user, f"Edición de usuario. Rol {new_role}. Activo: {new_active}.")
            messages.success(request, "Usuario actualizado.")
            return redirect("user_list")
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "title": f"Editar {user.get_username()}", "editing": user, "locked_owner": locked},
    )


def user_delete(request, pk):
    require(request.user, "accounts.manage_users")
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        if user.pk == request.user.pk:
            messages.error(request, "No puedes eliminar tu propia cuenta.")
        elif is_owner_account(user):
            messages.error(request, "La cuenta propietaria del servidor no se elimina desde aquí.")
        elif role_label(user) == "Superadmin" and active_owner_count(exclude_pk=user.pk) == 0:
            messages.error(request, "Tiene que quedar al menos un Superadmin activo.")
        else:
            try:
                username = user.get_username()
                user.delete()
            except ProtectedError:
                messages.error(
                    request,
                    "Este usuario ya tiene operaciones. Desactívalo: las ventas deben conservar quién las hizo.",
                )
            else:
                audit(request.user, "permission.change", detail=f"Se eliminó el usuario {username}.")
                messages.success(request, "Usuario eliminado.")
                return redirect("user_list")
        return redirect("user_edit", pk=user.pk)
    return render(request, "accounts/user_delete.html", {"account": user})


def profile(request):
    user = request.user
    initial = {"first_name": user.first_name, "last_name": user.last_name, "email": user.email}
    form = ProfileForm(request.POST or None, initial=None if request.method == "POST" else initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if data["new_password"]:
            if not user.check_password(data["current_password"]):
                form.add_error("current_password", "La contraseña actual no es correcta.")
            else:
                try:
                    validate_password(data["new_password"], user)
                except ValidationError as exc:
                    form.add_error("new_password", " ".join(exc.messages))
        if not form.errors:
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.email = data["email"]
            if data["new_password"]:
                user.set_password(data["new_password"])
            user.save()
            if data["pin"]:
                set_pin(user, data["pin"])
            if data["new_password"]:
                login(request, user)
            messages.success(request, "Datos actualizados.")
            return redirect("profile")
    business = getattr(request, "business", None) or get_business()
    return render(request, "accounts/profile.html", {"form": form, "otp_allowed": can_use_otp(user), "business": business})


def otp_status(request):
    if not can_use_otp(request.user):
        return render(request, "accounts/otp_unavailable.html")
    from django_otp.plugins.otp_static.models import StaticDevice
    from django_otp.plugins.otp_totp.models import TOTPDevice

    enabled = TOTPDevice.objects.filter(user=request.user, confirmed=True).exists()
    backup = StaticDevice.objects.filter(user=request.user, confirmed=True).first()
    remaining = backup.token_set.count() if backup else 0
    return render(request, "accounts/otp_status.html", {"enabled": enabled, "remaining": remaining})


@require_POST
def otp_start(request):
    if not can_use_otp(request.user):
        raise PermissionDenied("El segundo factor no aplica a tu rol.")
    from django_otp.plugins.otp_totp.models import TOTPDevice

    TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
    TOTPDevice.objects.create(user=request.user, name="principal", confirmed=False)
    return redirect("otp_confirm")


def otp_confirm(request):
    if not can_use_otp(request.user):
        raise PermissionDenied("El segundo factor no aplica a tu rol.")
    from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).order_by("-id").first()
    if device is None:
        return redirect("otp_status")
    form = OtpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            with transaction.atomic():
                TOTPDevice.objects.filter(user=request.user, confirmed=True).exclude(pk=device.pk).delete()
                device.confirmed = True
                device.save(update_fields=["confirmed"])
                StaticDevice.objects.filter(user=request.user).delete()
                backup = StaticDevice.objects.create(user=request.user, name="respaldo", confirmed=True)
                codes = []
                for _ in range(5):
                    code = StaticToken.random_token()
                    StaticToken.objects.create(device=backup, token=code)
                    codes.append(code)
            request.session["otp_backup_codes"] = codes
            messages.success(request, "Segundo factor activado.")
            return redirect("otp_codes")
        form.add_error("token", "El código no coincide. Revisa la hora del teléfono e inténtalo de nuevo.")
    return render(request, "accounts/otp_confirm.html", {"form": form})


@never_cache
def otp_qr(request):
    if not can_use_otp(request.user):
        raise PermissionDenied("El segundo factor no aplica a tu rol.")
    import qrcode
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).order_by("-id").first()
    if device is None:
        return HttpResponse(status=404)
    image = qrcode.make(device.config_url)
    response = HttpResponse(content_type="image/png")
    image.save(response, format="PNG")
    response["Cache-Control"] = "no-store"
    return response


def otp_codes(request):
    codes = request.session.pop("otp_backup_codes", None)
    if not codes:
        return redirect("otp_status")
    return render(request, "accounts/otp_codes.html", {"codes": codes})


def otp_disable(request):
    if not can_use_otp(request.user):
        raise PermissionDenied("El segundo factor no aplica a tu rol.")
    form = DisableOtpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not request.user.check_password(form.cleaned_data["password"]):
            form.add_error("password", "La contraseña no es correcta.")
        elif not _otp_ok(request.user, form.cleaned_data["token"]):
            form.add_error("token", "Código incorrecto.")
        else:
            from django_otp.plugins.otp_static.models import StaticDevice
            from django_otp.plugins.otp_totp.models import TOTPDevice

            TOTPDevice.objects.filter(user=request.user).delete()
            StaticDevice.objects.filter(user=request.user).delete()
            messages.success(request, "Segundo factor desactivado.")
            return redirect("otp_status")
    return render(request, "accounts/otp_disable.html", {"form": form})

