from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.core.money import money

register = template.Library()

ICONS = {
    "home": '<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z"/>',
    "box": '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M12 12 3 7.5M12 12l9-4.5M12 12v9"/>',
    "tag": '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor" stroke="none"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 16 9 5 9-5"/>',
    "alert": '<path d="M12 4 3 19h18z"/><path d="M12 10v4M12 16.5v.5"/>',
    "users": '<path d="M8 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 11a2.5 2.5 0 1 0 0-5M16.2 13.2A5 5 0 0 1 21.5 19"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>',
    "clipboard": '<path d="M8 4h8v2H8z"/><path d="M7 6H6v14h12V6h-1"/>',
    "cart": '<circle cx="8" cy="19" r="1.4"/><circle cx="17" cy="19" r="1.4"/><path d="M3 5h2l2.2 10h10.3l2-7H7"/>',
    "chart": '<path d="M4 19V5M4 19h16"/><path d="M8 15v-4M12 15V8M16 15v-6"/>',
    "lock": '<rect x="6" y="10" width="12" height="9" rx="1.5"/><path d="M8 10V8a4 4 0 0 1 8 0v2"/>',
}


@register.simple_tag
def icon(name):
    body = ICONS.get(name, ICONS["box"])
    return format_html(
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round">{}</svg>',
        mark_safe(body),
    )


@register.simple_tag(takes_context=True)
def moneyfmt(context, value):
    business = context.get("business")
    if value is None or value == "":
        return "—"
    places = business.decimal_places if business else 2
    symbol = business.currency_symbol if business else "$"
    amount = money(value, places)
    return f"{symbol}{amount:,.{places}f}"
