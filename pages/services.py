from django.db.models import Q

from .models import Page


def published_pages_for_tenant(tenant):
    return Page.objects.for_tenant(tenant).filter(is_published=True)


def search_pages(*, tenant, query):
    query = (query or '').strip()
    if not query:
        return Page.objects.none()
    return published_pages_for_tenant(tenant).filter(
        Q(title__icontains=query) | Q(content__icontains=query)
    )
