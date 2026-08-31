from django.db.models import Q
from django.utils import timezone

from .models import BreakingNews, NewsArticle


def published_articles_for_tenant(tenant):
    return (
        NewsArticle.objects.for_tenant(tenant)
        .select_related('category', 'author')
        .prefetch_related('tags', 'reporters')
        .filter(status=NewsArticle.Status.PUBLISHED)
    )


def search_articles(*, tenant, query):
    queryset = published_articles_for_tenant(tenant)
    query = (query or '').strip()
    if not query:
        return queryset.none()
    return queryset.filter(
        Q(title__icontains=query)
        | Q(short_description__icontains=query)
        | Q(content__icontains=query)
        | Q(tags__name__icontains=query)
        | Q(category__name__icontains=query)
    ).distinct()


def active_breaking_news_for_tenant(tenant):
    now = timezone.now()
    return (
        BreakingNews.objects.for_tenant(tenant)
        .select_related('article')
        .filter(is_active=True, starts_at__lte=now)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .order_by('ticker_order', '-starts_at')
    )
