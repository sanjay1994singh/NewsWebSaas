from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from domains.models import TenantDomain
from subscriptions.models import PlanPrice, TenantSubscription
from tenants.models import Tenant

from .models import PageView


def tenant_cache_key(tenant, key):
    return f"tenant:{tenant.id}:{key}"


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
