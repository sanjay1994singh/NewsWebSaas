from django import template


register = template.Library()


@register.filter
def get_item(value, key):
    if value is None:
        return None
    return value.get(key)
