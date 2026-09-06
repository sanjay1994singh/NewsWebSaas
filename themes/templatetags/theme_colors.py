import re
from django import template
register = template.Library()

@register.simple_tag
def readable_color(value, fallback='#0b6b57'):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(value or '')):
        return fallback
    rgb = [int(value[i:i+2], 16) for i in (1, 3, 5)]
    def luminance():
        channels = [v / 255 for v in rgb]
        channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * w for v, w in zip(channels, [.2126, .7152, .0722]))
    while luminance() > .183:
        rgb = [int(v * .94) for v in rgb]
    return '#' + ''.join(f'{v:02x}' for v in rgb)
