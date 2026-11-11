import json
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.access import require
from apps.catalog.models import Product, Promotion
from apps.core.audit import audit
from apps.core.models import get_business
from apps.offline.auth import device_can_sync, device_from_request, hash_token
from apps.offline.models import Device, SyncConflict
from apps.operations.cashbox import current_shift
from apps.operations.checkout import CheckoutError, confirm_sale
from apps.operations.models import Sale


def device_list(request):
    require(request.user, "offline.authorize_device")
    devices = Device.objects.select_related("user")
    users = User.objects.filter(is_active=True).order_by("username")
    return render(request, "offline/devices.html", {"devices": devices, "users": users, "fresh_token": request.session.pop("fresh_device_token", None), "fresh_name": request.session.pop("fresh_device_name", "")})


@require_POST
def device_create(request):
    require(request.user, "offline.authorize_device")
    config = get_business()
    user = get_object_or_404(User, pk=request.POST.get("user"), is_active=True)
    if not user.has_perm("operations.sell") and not user.is_superuser:
        messages.error(request, "Ese usuario no puede cobrar.")
        return redirect("device_list")
    token = secrets.token_urlsafe(32)
    name = (request.POST.get("name") or "Caja").strip()[:80]
    device = Device.objects.create(
        name=name,
        token_hash=hash_token(token),
        user=user,
        created_by=request.user,
        expires_at=timezone.now() + timedelta(days=config.offline_auth_days),
    )
    request.session["fresh_device_token"] = token
    request.session["fresh_device_name"] = device.name
    audit(request.user, "device.authorize", device, f"{device.name} para {user.get_username()} hasta {timezone.localtime(device.expires_at):%d/%m/%Y %H:%M}.")
    messages.success(request, "Dispositivo autorizado. El token se muestra una sola vez.")
    return redirect("device_list")


@require_POST
def device_revoke(request, pk):
    require(request.user, "offline.authorize_device")
    device = get_object_or_404(Device, pk=pk, revoked_at__isnull=True)
    device.revoked_at = timezone.now()
    device.save(update_fields=["revoked_at"])
    messages.success(request, "Dispositivo revocado. No podrá sincronizar.")
    return redirect("device_list")


def catalog_api(request):
    if not request.user.is_authenticated or not request.user.has_perm("operations.sell"):
        return JsonResponse({"error": "No autorizado."}, status=401)
    device = device_from_request(request)
    if device is None or not device.is_active or device.user_id != request.user.id:
        return JsonResponse({"error": "Este navegador no está autorizado para operar sin internet."}, status=403)
    config = get_business()
    now = timezone.now()
    products = [
        {
            "id": product.pk,
            "name": product.name,
            "code": product.code,
            "price": f"{product.price:.2f}",
            "stock": product.stock,
            "active": product.is_active,
        }
        for product in Product.objects.filter(is_active=True).order_by("name")
    ]
    promotions = []
    for promo in Promotion.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).prefetch_related("products"):
        promotions.append(
            {
                "id": promo.pk,
                "name": promo.name,
                "discount_type": promo.discount_type,
                "discount_value": f"{promo.discount_value:.2f}",
                "product_ids": list(promo.products.values_list("pk", flat=True)),
                "starts_at": promo.starts_at.isoformat(),
                "ends_at": promo.ends_at.isoformat(),
            }
        )
    shift = current_shift()
    return JsonResponse(
        {
            "fetched_at": now.isoformat(),
            "currency": config.currency_code,
            "symbol": config.currency_symbol,
            "decimal_places": config.decimal_places,
            "prices_include_tax": config.prices_include_tax,
            "tax_rate": f"{config.tax_rate:.2f}",
            "stale_hours": config.offline_stale_hours,
            "products": products,
            "promotions": promotions,
            "shift_open": bool(shift),
        }
    )


@csrf_exempt
def sync_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Usa POST."}, status=405)
    device = device_from_request(request)
    if not device_can_sync(device):
        return JsonResponse({"error": "Dispositivo no autorizado o revocado."}, status=401)
    if not device.user.is_active or not (device.user.has_perm("operations.sell") or device.user.is_superuser):
        return JsonResponse({"error": "El usuario del dispositivo no puede cobrar."}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "El cuerpo no es JSON."}, status=400)
    config = get_business()
    shift = current_shift()
    results = []
    for item in payload.get("sales", []):
        client_uuid = item.get("client_uuid")
        try:
            sale = confirm_sale(
                user=device.user,
                lines=item.get("lines") or [],
                payments=item.get("payments") or [],
                shift=shift,
                customer_name=item.get("customer_name", ""),
                customer_phone=item.get("customer_phone", ""),
                client_uuid=client_uuid,
                origin=Sale.OFFLINE,
                created_at=item.get("created_at"),
                catalog_as_of=item.get("catalog_as_of"),
                price_mode="frozen",
                stock_policy="conflict",
                record_cash=True,
                config=config,
            )
        except (CheckoutError, KeyError, TypeError, ValueError) as exc:
            results.append({"client_uuid": client_uuid, "status": "error", "message": str(exc)})
            continue
        results.append(
            {
                "client_uuid": str(sale.client_uuid),
                "status": sale.sync_status,
                "folio": sale.folio,
                "message": sale.sync_note,
            }
        )
    device.last_sync_at = timezone.now()
    device.save(update_fields=["last_sync_at"])
    return JsonResponse({"results": results})


def conflict_list(request):
    require(request.user, "operations.view_all_sales")
    conflicts = SyncConflict.objects.select_related("sale", "product", "resolved_by")
    return render(request, "offline/conflicts.html", {"conflicts": conflicts[:100]})


@require_POST
def conflict_resolve(request, pk):
    require(request.user, "operations.view_all_sales")
    conflict = get_object_or_404(SyncConflict, pk=pk, status=SyncConflict.OPEN)
    note = (request.POST.get("note") or "").strip()
    if len(note) < 3:
        messages.error(request, "Escribe qué se revisó.")
        return redirect("conflict_list")
    conflict.status = SyncConflict.RESOLVED
    conflict.resolution_note = note
    conflict.resolved_by = request.user
    conflict.resolved_at = timezone.now()
    conflict.save()
    if conflict.sale_id and not conflict.sale.conflicts.filter(status=SyncConflict.OPEN).exists():
        conflict.sale.sync_status = Sale.SYNC_SYNCED
        conflict.sale.save(update_fields=["sync_status"])
    messages.success(request, "Conflicto marcado como revisado. La venta no se modificó.")
    return redirect("conflict_list")


def service_worker(request):
    script = Path(settings.BASE_DIR, "static", "sw.js").read_text(encoding="utf-8")
    response = HttpResponse(script, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
