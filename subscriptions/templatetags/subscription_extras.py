from django import template


register = template.Library()


@register.filter
def get_item(value, key):
    if value is None:
        return None
    return value.get(key)


@register.filter
def paise_to_rupees(value):
    try:
        amount = int(value) / 100
    except (TypeError, ValueError):
        return value
    return f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"
