try:
    import bleach
except ImportError:
    bleach = None


ALLOWED_TAGS = [
    'a', 'abbr', 'blockquote', 'br', 'code', 'div', 'em', 'h2', 'h3', 'h4',
    'hr', 'img', 'li', 'ol', 'p', 'pre', 'span', 'strong', 'sub', 'sup',
    'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul',
]
ALLOWED_ATTRIBUTES = {
    '*': ['class'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
}
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def sanitize_html(value):
    value = value or ''
    if bleach is None:
        from html import escape
        return escape(value)
    cleaned = bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return bleach.linkify(cleaned)
