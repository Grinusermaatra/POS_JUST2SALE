import io
import secrets

import qrcode
from barcode import Code128
from barcode.writer import ImageWriter
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.access import require
from apps.catalog.forms import ProductForm, PromotionForm
from apps.catalog.models import PackageComponent, PriceHistory, Product, Promotion
from apps.catalog.pricing import best_promotion, price_after_promotion
from apps.core.audit import audit
from apps.core.models import get_business
from apps.inventory.services import InventoryError, apply_stock_change


def _can_see_cost(user):
    return user.has_perm("inventory.view_costs")


def _can_manage(user):
    return user.has_perm("catalog.manage_catalog")


def _require_catalog_read(user):
    if user.has_perm("catalog.consult_products") or user.has_perm("catalog.manage_catalog"):
        return
    require(user, "catalog.consult_products")


def _new_code():
    while True:
        code = "P" + secrets.token_hex(4).upper()
        if not Product.objects.filter(code=code).exists():
            return code


def _places(request):
    business = getattr(request, "business", None) or get_business()
    return business.decimal_places


def product_list(request):
    _require_catalog_read(request.user)
    business = getattr(request, "business", None) or get_business()
    now = timezone.now()
    query = (request.GET.get("q") or "").strip()
    show_inactive = request.GET.get("inactivos") == "1"
    products = Product.objects.all()
    if not show_inactive:
        products = products.filter(is_active=True)
    if query:
        products = products.filter(Q(name__icontains=query) | Q(code__icontains=query))
    products = products.prefetch_related(
        Prefetch(
            "promotions",
            queryset=Promotion.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now),
        )
    ).order_by("name")
    rows = []
    for product in products:
        promo, _ = best_promotion(product, at=now, places=business.decimal_places)
        rows.append({"product": product, "promo": promo, "low": product.is_low(business.low_stock_default)})
    return render(
        request,
        "catalog/product_list.html",
        {
            "rows": rows,
            "query": query,
            "show_inactive": show_inactive,
            "can_manage": _can_manage(request.user),
            "show_cost": _can_see_cost(request.user),
        },
    )


def product_create(request):
    require(request.user, "catalog.manage_catalog")
    form = ProductForm(request.POST or None, show_cost=_can_see_cost(request.user), creating=True)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                product = form.save(commit=False)
                if not product.code:
                    product.code = _new_code()
                product.save()
                PriceHistory.objects.create(
                    product=product,
                    old_price=product.price,
                    new_price=product.price,
                    reason="Precio inicial",
                    user=request.user,
                )
                quantity = form.cleaned_data.get("initial_quantity") or 0
                if quantity:
                    apply_stock_change(
                        product=product,
                        quantity_delta=quantity,
                        movement_type="entry",
                        reason=form.cleaned_data["initial_reason"].strip(),
                        user=request.user,
                        ref_type="product",
                        ref_id=str(product.pk),
                    )
                    audit(request.user, "inventory.adjust", product, f"Existencia inicial {quantity}.")
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Producto guardado.")
            return redirect("product_detail", pk=product.pk)
    return render(request, "catalog/product_form.html", {"form": form, "title": "Nuevo producto"})


def product_edit(request, pk):
    require(request.user, "catalog.manage_catalog")
    product = get_object_or_404(Product, pk=pk)
    old_price = product.price
    old_kind = product.kind
    form = ProductForm(
        request.POST or None,
        instance=product,
        show_cost=_can_see_cost(request.user),
        creating=False,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            current = Product.objects.select_for_update().get(pk=product.pk)
            saved = form.save(commit=False)
            saved.stock = current.stock
            saved.save()
            if saved.kind != Product.KIND_PACKAGE:
                saved.components.all().delete()
            if saved.price != old_price:
                reason = form.cleaned_data["price_reason"].strip()
                PriceHistory.objects.create(
                    product=saved,
                    old_price=old_price,
                    new_price=saved.price,
                    reason=reason,
                    user=request.user,
                )
                audit(
                    request.user,
                    "price.change",
                    saved,
                    f"Precio de {old_price} a {saved.price}. {reason}",
                )
        if old_kind != saved.kind and saved.kind != Product.KIND_PACKAGE:
            messages.info(request, "Dejó de ser paquete. Se quitó su composición.")
        messages.success(request, "Producto actualizado.")
        return redirect("product_detail", pk=saved.pk)
    return render(request, "catalog/product_form.html", {"form": form, "title": f"Editar {product.name}", "product": product})


def product_detail(request, pk):
    _require_catalog_read(request.user)
    product = get_object_or_404(Product.objects.prefetch_related("components__component", "price_history"), pk=pk)
    business = getattr(request, "business", None) or get_business()
    promo, discount = best_promotion(product, places=business.decimal_places)
    components = list(product.components.select_related("component"))
    component_choices = Product.objects.filter(kind=Product.KIND_PRODUCT, is_active=True).exclude(pk=product.pk)
    return render(
        request,
        "catalog/product_detail.html",
        {
            "product": product,
            "promo": promo,
            "discount": discount,
            "promo_price": price_after_promotion(product, places=business.decimal_places),
            "components": components,
            "component_choices": component_choices,
            "can_manage": _can_manage(request.user),
            "show_cost": _can_see_cost(request.user),
            "show_history": _can_manage(request.user) or request.user.has_perm("catalog.manage_promotions"),
            "low": product.is_low(business.low_stock_default),
            "threshold": product.threshold(business.low_stock_default),
            "supplies_on": business.supplies_enabled,
            "can_recipe": business.supplies_enabled and request.user.has_perm("inventory.manage_supplies"),
        },
    )


@require_POST
def package_add(request, pk):
    require(request.user, "catalog.manage_catalog")
    package = get_object_or_404(Product, pk=pk, kind=Product.KIND_PACKAGE)
    component = Product.objects.filter(pk=request.POST.get("component"), kind=Product.KIND_PRODUCT).first()
    try:
        quantity = int(request.POST.get("quantity") or "0")
    except ValueError:
        quantity = 0
    if component is None or component.pk == package.pk:
        messages.error(request, "Elige un producto simple.")
    elif quantity < 1:
        messages.error(request, "La cantidad del componente tiene que ser al menos 1.")
    else:
        PackageComponent.objects.update_or_create(
            package=package, component=component, defaults={"quantity": quantity}
        )
        messages.success(request, "Componente guardado. Vender el paquete no descuenta estos productos.")
    return redirect("product_detail", pk=package.pk)


@require_POST
def package_remove(request, pk, component_id):
    require(request.user, "catalog.manage_catalog")
    package = get_object_or_404(Product, pk=pk)
    PackageComponent.objects.filter(package=package, pk=component_id).delete()
    messages.success(request, "Componente quitado.")
    return redirect("product_detail", pk=package.pk)


def product_qr(request, pk):
    require(request.user, "catalog.manage_catalog")
    product = get_object_or_404(Product, pk=pk)
    image = qrcode.QRCode(box_size=8, border=2)
    image.add_data(product.code)
    image.make(fit=True)
    rendered = image.make_image(fill_color="#241C14", back_color="white")
    buffer = io.BytesIO()
    rendered.save(buffer, format="PNG")
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    mode = "attachment" if request.GET.get("descarga") else "inline"
    response["Content-Disposition"] = f'{mode}; filename="{product.code}-qr.png"'
    return response


def product_barcode(request, pk):
    require(request.user, "catalog.manage_catalog")
    product = get_object_or_404(Product, pk=pk)
    buffer = io.BytesIO()
    Code128(product.code, writer=ImageWriter()).write(buffer)
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    mode = "attachment" if request.GET.get("descarga") else "inline"
    response["Content-Disposition"] = f'{mode}; filename="{product.code}-barras.png"'
    return response


def product_print(request, pk):
    require(request.user, "catalog.manage_catalog")
    product = get_object_or_404(Product, pk=pk)
    return render(request, "catalog/product_print.html", {"product": product})


def promotion_list(request):
    require(request.user, "catalog.manage_promotions")
    promotions = Promotion.objects.prefetch_related("products").all()
    return render(request, "catalog/promotion_list.html", {"promotions": promotions, "now": timezone.now()})


def promotion_create(request):
    require(request.user, "catalog.manage_promotions")
    form = PromotionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        audit(request.user, "promotion.change", promo, f"Alta de promoción {promo.name}.")
        messages.success(request, "Promoción guardada. En la caja solo aplica la que más descuenta.")
        return redirect("promotion_list")
    return render(request, "catalog/promotion_form.html", {"form": form, "title": "Nueva promoción"})


def promotion_edit(request, pk):
    require(request.user, "catalog.manage_promotions")
    promo = get_object_or_404(Promotion, pk=pk)
    form = PromotionForm(request.POST or None, instance=promo)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        audit(request.user, "promotion.change", saved, f"Cambio de promoción {saved.name}.")
        messages.success(request, "Promoción actualizada.")
        return redirect("promotion_list")
    return render(request, "catalog/promotion_form.html", {"form": form, "title": f"Editar {promo.name}"})
