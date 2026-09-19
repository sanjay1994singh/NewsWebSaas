from django.utils.text import slugify


def compact_publication_slug(value, fallback='publication', max_length=160):
    normalized = (value or '').replace('&', ' and ')
    slug = slugify(normalized).replace('-', '').strip()
    return (slug or fallback)[:max_length]
