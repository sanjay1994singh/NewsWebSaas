from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .entitlements import invalidate_entitlement_cache
from .models import AddOn, PlanFeature, TenantAddOn, TenantFeatureOverride, TenantSubscription


def _invalidate_plan_subscribers(plan):
    subscriptions = TenantSubscription.objects.select_related('tenant').filter(plan=plan)
    for subscription in subscriptions:
        invalidate_entitlement_cache(subscription.tenant)


@receiver([post_save, post_delete], sender=PlanFeature)
def invalidate_plan_feature_entitlements(sender, instance, **kwargs):
    _invalidate_plan_subscribers(instance.plan)


@receiver([post_save, post_delete], sender=TenantSubscription)
def invalidate_subscription_entitlements(sender, instance, **kwargs):
    invalidate_entitlement_cache(instance.tenant)


@receiver([post_save, post_delete], sender=TenantAddOn)
def invalidate_tenant_add_on_entitlements(sender, instance, **kwargs):
    invalidate_entitlement_cache(instance.tenant)


@receiver([post_save, post_delete], sender=TenantFeatureOverride)
def invalidate_tenant_override_entitlements(sender, instance, **kwargs):
    invalidate_entitlement_cache(instance.tenant)


@receiver([post_save, post_delete], sender=AddOn)
def invalidate_add_on_entitlements(sender, instance, **kwargs):
    tenant_add_ons = TenantAddOn.objects.select_related('tenant').filter(add_on=instance)
    for tenant_add_on in tenant_add_ons:
        invalidate_entitlement_cache(tenant_add_on.tenant)
