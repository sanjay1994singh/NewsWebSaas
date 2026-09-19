from django.utils.text import slugify


def compact_publication_slug(value, fallback='publication', max_length=160):
    slug = slugify(value or '').replace('-', '').strip()
    return (slug or fallback)[:max_length]
