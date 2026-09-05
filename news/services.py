from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from subscriptions.entitlements import tenant_feature_limit
from subscriptions.models import TenantSubscription
from subscriptions.services import subscription_monthly_usage_window

from .models import BreakingNews, NewsArticle


NEWS_ARTICLE_LIMIT_FEATURE = 'news_articles'
NEWS_LIMIT_COUNTED_STATUSES = {
    NewsArticle.Status.REVIEW,
    NewsArticle.Status.SCHEDULED,
    NewsArticle.Status.PUBLISHED,
}


def article_public_path(article):
    return f"/articles/{article.uuid}/"


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


def news_article_monthly_usage(tenant, now=None):
    now = now or timezone.now()
    try:
        subscription = tenant.subscription
    except TenantSubscription.DoesNotExist:
        subscription = None
    window_start, window_end = subscription_monthly_usage_window(subscription, now)
    count = (
        NewsArticle.objects
        .for_tenant(tenant)
        .filter(
            content_type=NewsArticle.ContentType.NEWS,
            status__in=NEWS_LIMIT_COUNTED_STATUSES,
            created_at__gte=window_start,
            created_at__lt=window_end,
        )
        .count()
    )
    return {
        'limit': tenant_feature_limit(tenant, NEWS_ARTICLE_LIMIT_FEATURE),
        'used': count,
        'window_start': window_start,
        'window_end': window_end,
    }


def validate_news_article_monthly_limit(tenant, article, now=None):
    if article.content_type != NewsArticle.ContentType.NEWS:
        return
    if article.status not in NEWS_LIMIT_COUNTED_STATUSES:
        return
    usage = news_article_monthly_usage(tenant, now)
    limit = usage['limit']
    if limit in (None, ''):
        return
    limit = int(limit)
    queryset = (
        NewsArticle.objects
        .for_tenant(tenant)
        .filter(
            content_type=NewsArticle.ContentType.NEWS,
            status__in=NEWS_LIMIT_COUNTED_STATUSES,
            created_at__gte=usage['window_start'],
            created_at__lt=usage['window_end'],
        )
    )
    if article.pk:
        queryset = queryset.exclude(pk=article.pk)
    if queryset.count() >= limit:
        raise ValidationError(
            f'Your monthly news article limit is {limit}. Upgrade your plan or wait for the next billing month.'
        )
