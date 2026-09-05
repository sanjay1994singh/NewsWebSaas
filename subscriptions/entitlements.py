from django.core.cache import cache
from django.utils import timezone

from .models import PlanFeature, TenantAddOn, TenantFeatureOverride, TenantSubscription


DEFAULT_ENTITLEMENTS = {
    'starter': {
        'staff': 3,
        'multiple_staff': 3,
        'monthly_articles': 100,
        'news_articles': 100,
        'storage_mb': 1024,
        'themes': ['theme_classic'],
        'premium_themes': False,
        'custom_domain': False,
        'video': False,
        'youtube_videos': False,
        'youtube_shorts': False,
        'live_tv': False,
        'advertisements': False,
        'advertisement_manager': False,
        'adsense': False,
        'analytics': False,
        'advanced_seo': False,
        'api_access': False,
        'epaper': False,
        'homepage_builder': True,
    },
    'professional': {
        'staff': 10,
        'multiple_staff': 10,
        'monthly_articles': 1000,
        'news_articles': 1000,
        'storage_mb': 10240,
        'themes': ['theme_classic', 'theme_modern'],
        'premium_themes': True,
        'custom_domain': True,
        'video': True,
        'youtube_videos': True,
        'youtube_shorts': True,
        'live_tv': False,
        'advertisements': True,
        'advertisement_manager': True,
        'adsense': True,
        'analytics': True,
        'advanced_seo': True,
        'api_access': False,
        'epaper': False,
        'homepage_builder': True,
    },
    'business': {
        'staff': 50,
        'multiple_staff': 50,
        'monthly_articles': 10000,
        'news_articles': 10000,
        'storage_mb': 102400,
        'themes': ['theme_classic', 'theme_modern', 'theme_tv'],
        'premium_themes': True,
        'custom_domain': True,
        'video': True,
        'youtube_videos': True,
        'youtube_shorts': True,
        'live_tv': True,
        'advertisements': True,
        'advertisement_manager': True,
        'adsense': True,
        'analytics': True,
        'advanced_seo': True,
        'api_access': True,
        'epaper': True,
        'homepage_builder': True,
    },
}

ACTIVE_SUBSCRIPTION_STATUSES = {
    TenantSubscription.Status.TRIAL,
    TenantSubscription.Status.ACTIVE,
    TenantSubscription.Status.GRACE_PERIOD,
}


def _is_current(starts_at, expires_at, now=None):
    now = now or timezone.now()
    if starts_at and starts_at > now:
        return False
    if expires_at and expires_at <= now:
        return False
    return True


def _entitlement(is_enabled=False, limit_value=None, configuration=None, source='default_deny'):
    return {
        'is_enabled': bool(is_enabled),
        'limit_value': limit_value,
        'configuration': configuration or {},
        'source': source,
    }


def _legacy_value_to_entitlement(value):
    if isinstance(value, bool):
        return _entitlement(is_enabled=value, source='legacy_plan_json')
    if isinstance(value, int):
        return _entitlement(is_enabled=value > 0, limit_value=value, source='legacy_plan_json')
    if value:
        return _entitlement(is_enabled=True, configuration={'value': value}, source='legacy_plan_json')
    return _entitlement(source='legacy_plan_json')


def snapshot_plan_entitlements(plan):
    entitlements = {}
    plan_features = (
        PlanFeature.objects
        .select_related('feature')
        .filter(plan=plan, feature__is_active=True)
    )
    for plan_feature in plan_features:
        entitlements[plan_feature.feature.code] = _entitlement(
            is_enabled=plan_feature.is_enabled,
            limit_value=plan_feature.limit_value,
            configuration=plan_feature.configuration_json,
            source='purchased_plan_snapshot',
        )
    if not entitlements and plan.entitlements:
        for code, value in plan.entitlements.items():
            entitlement = _legacy_value_to_entitlement(value)
            entitlement['source'] = 'purchased_plan_snapshot'
            entitlements[code] = entitlement
    return entitlements


def _subscription_for_tenant(tenant):
    try:
        subscription = tenant.subscription
    except TenantSubscription.DoesNotExist:
        return None
    if subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return None
    return subscription


def entitlement_cache_key(tenant):
    subscription = getattr(tenant, 'subscription', None)
    subscription_marker = 'no-subscription'
    if subscription:
        updated_at = subscription.updated_at.isoformat() if subscription.updated_at else 'new'
        subscription_marker = f"{subscription.pk}:{subscription.status}:{updated_at}"
    return f"tenant-entitlements:{tenant.pk}:{subscription_marker}"


def invalidate_entitlement_cache(tenant):
    cache.delete(entitlement_cache_key(tenant))


def get_effective_entitlements(tenant):
    entitlements = {}
    subscription = _subscription_for_tenant(tenant)

    if subscription:
        if subscription.entitlement_snapshot:
            entitlements.update(subscription.entitlement_snapshot)
        else:
            plan_features = (
                PlanFeature.objects
                .select_related('feature')
                .filter(plan=subscription.plan, feature__is_active=True)
            )
            for plan_feature in plan_features:
                entitlements[plan_feature.feature.code] = _entitlement(
                    is_enabled=plan_feature.is_enabled,
                    limit_value=plan_feature.limit_value,
                    configuration=plan_feature.configuration_json,
                    source='plan_feature',
                )

            if not entitlements and subscription.plan.entitlements:
                for code, value in subscription.plan.entitlements.items():
                    entitlements[code] = _legacy_value_to_entitlement(value)

    now = timezone.now()
    tenant_add_ons = (
        TenantAddOn.objects
        .select_related('add_on__feature')
        .filter(tenant=tenant, is_active=True, add_on__is_active=True, add_on__feature__is_active=True)
    )
    for tenant_add_on in tenant_add_ons:
        if not _is_current(tenant_add_on.starts_at, tenant_add_on.expires_at, now):
            continue
        add_on = tenant_add_on.add_on
        entitlements[add_on.feature.code] = _entitlement(
            is_enabled=True,
            limit_value=add_on.limit_value,
            configuration=add_on.configuration_json,
            source='tenant_add_on',
        )

    overrides = (
        TenantFeatureOverride.objects
        .select_related('feature')
        .filter(tenant=tenant, feature__is_active=True)
        .order_by('created_at')
    )
    for override in overrides:
        if not _is_current(override.starts_at, override.expires_at, now):
            continue
        entitlements[override.feature.code] = _entitlement(
            is_enabled=False if override.override_type == TenantFeatureOverride.OverrideType.RESTRICT else override.is_enabled,
            limit_value=override.limit_value,
            configuration=override.configuration_json,
            source=f"tenant_override:{override.override_type}",
        )

    return entitlements


def get_effective_entitlement(tenant, feature_code):
    return get_effective_entitlements(tenant).get(feature_code, _entitlement())


def tenant_has_feature(tenant, feature_code):
    return get_effective_entitlement(tenant, feature_code)['is_enabled']


def tenant_feature_limit(tenant, feature_code):
    entitlement = get_effective_entitlement(tenant, feature_code)
    if not entitlement['is_enabled']:
        return None
    return entitlement['limit_value']


def get_feature_limit(tenant, feature_code):
    return tenant_feature_limit(tenant, feature_code)
