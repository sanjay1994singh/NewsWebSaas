from datetime import timedelta
import hashlib
from urllib.parse import urlparse

from django.db import IntegrityError
from django.db.models import Count, F, Sum
from django.utils import timezone

from domains.models import TenantDomain
from news.models import NewsArticle
from subscriptions.models import PlanPrice, TenantSubscription
from tenants.models import Tenant

from .models import PageView


def tenant_cache_key(tenant, key):
    return f"tenant:{tenant.id}:{key}"


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',', 1)[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _device_type(user_agent):
    value = (user_agent or '').lower()
    if any(token in value for token in ('mobile', 'android', 'iphone')):
        return 'mobile'
    if any(token in value for token in ('ipad', 'tablet')):
        return 'tablet'
    return 'desktop'


def _referrer_domain(request):
    referrer = request.META.get('HTTP_REFERER', '')
    return (urlparse(referrer).hostname or '').lower()


def visitor_key_for_request(request):
    existing = request.COOKIES.get('pnx_visitor')
    if existing:
        return hashlib.sha256(existing.encode('utf-8')).hexdigest(), None
    source = '|'.join([
        _client_ip(request),
        request.META.get('HTTP_USER_AGENT', ''),
        request.META.get('HTTP_ACCEPT_LANGUAGE', ''),
    ])
    visitor_id = hashlib.sha256(source.encode('utf-8')).hexdigest()
    return hashlib.sha256(visitor_id.encode('utf-8')).hexdigest(), visitor_id


def record_article_view(request, article):
    visitor_key, new_cookie_value = visitor_key_for_request(request)
    created = False
    try:
        _, created = PageView.objects.get_or_create(
            tenant=article.tenant,
            article=article,
            unique_visitor_key=visitor_key,
            defaults={
                'path': request.path,
                'category': article.category,
                'referrer_domain': _referrer_domain(request),
                'device_type': _device_type(request.META.get('HTTP_USER_AGENT', '')),
                'occurred_at': timezone.now(),
            },
        )
    except IntegrityError:
        created = False
    if created:
        NewsArticle.objects.filter(pk=article.pk).update(view_count=F('view_count') + 1)
        article.refresh_from_db(fields=['view_count'])
    return created, new_cookie_value


def platform_metrics():
    subscriptions = TenantSubscription.objects.select_related('plan')
    monthly_amount = PlanPrice.objects.filter(
        plan__tenant_subscriptions__status=TenantSubscription.Status.ACTIVE,
        billing_cycle=PlanPrice.BillingCycle.MONTHLY,
    ).aggregate(total=Sum('amount'))['total'] or 0
    yearly_amount = PlanPrice.objects.filter(
        plan__tenant_subscriptions__status=TenantSubscription.Status.ACTIVE,
        billing_cycle=PlanPrice.BillingCycle.YEARLY,
    ).aggregate(total=Sum('amount'))['total'] or 0
    mrr = monthly_amount + int(yearly_amount / 12)
    return {
        'total_tenants': Tenant.objects.count(),
        'active_tenants': Tenant.objects.filter(status=Tenant.Status.ACTIVE).count(),
        'trials': Tenant.objects.filter(status=Tenant.Status.TRIAL).count(),
        'paid_customers': subscriptions.filter(status=TenantSubscription.Status.ACTIVE).count(),
        'suspended_tenants': Tenant.objects.filter(status=Tenant.Status.SUSPENDED).count(),
        'plan_distribution': list(subscriptions.values('plan__name').annotate(count=Count('id'))),
        'mrr_estimate': mrr,
        'arr_estimate': mrr * 12,
        'recent_subscriptions': subscriptions.order_by('-created_at')[:10],
        'payment_issues': subscriptions.filter(status__in=[TenantSubscription.Status.PAYMENT_ISSUE, TenantSubscription.Status.GRACE_PERIOD, TenantSubscription.Status.RESTRICTED]),
        'domains_pending_verification': TenantDomain.objects.filter(is_verified=False).count(),
    }


def tenant_analytics(tenant):
    now = timezone.now()
    base = PageView.objects.for_tenant(tenant)
    return {
        'today_views': base.filter(occurred_at__date=now.date()).count(),
        'weekly_views': base.filter(occurred_at__gte=now - timedelta(days=7)).count(),
        'monthly_views': base.filter(occurred_at__gte=now - timedelta(days=30)).count(),
        'top_articles': list(base.exclude(article=None).values('article__title').annotate(views=Count('id')).order_by('-views')[:10]),
        'top_categories': list(base.exclude(category=None).values('category__name').annotate(views=Count('id')).order_by('-views')[:10]),
        'referrers': list(base.exclude(referrer_domain='').values('referrer_domain').annotate(views=Count('id')).order_by('-views')[:10]),
        'devices': list(base.exclude(device_type='').values('device_type').annotate(views=Count('id')).order_by('-views')[:10]),
    }
