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


@register.filter
def currency_symbol(value):
    return "₹" if value == "INR" else value


@register.simple_tag
def money_amount(currency, value):
    amount = paise_to_rupees(value)
    return f"{currency_symbol(currency)} {amount}"
