import hmac
import json
from hashlib import sha256

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from tenants.models import Tenant, TenantMembership

from .entitlements import get_effective_entitlements
from .models import (
    CustomerAcquisition,
    OnboardingReviewEvent,
    PlanChangeRequest,
    PlanPrice,
    RazorpayPlanMapping,
    TenantAddOn,
    TenantOnboarding,
    TenantSubscription,
    WebhookEvent,
)


def verify_razorpay_signature(*, body, signature, secret):
    expected = hmac.new(secret.encode('utf-8'), body, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ''):
        raise ValidationError("Invalid Razorpay signature.")
    return True


def get_active_mapping(price, environment):
    return RazorpayPlanMapping.objects.get(price=price, environment=environment, is_active=True)


def create_subscription_checkout(*, tenant, price_id, quantity=1):
    price = PlanPrice.objects.select_related('plan').get(pk=price_id, is_active=True, plan__is_active=True)
    mapping = get_active_mapping(price, settings.RAZORPAY_ENVIRONMENT)
    return {
        'tenant_id': tenant.id,
        'plan_id': price.plan_id,
        'billing_cycle': price.billing_cycle,
        'amount': price.amount,
        'currency': price.currency,
        'quantity': quantity,
        'razorpay_plan_id': mapping.razorpay_plan_id,
        'environment': settings.RAZORPAY_ENVIRONMENT,
    }


@transaction.atomic
def reserve_customer_acquisition(*, username, password, business_name, publication_name, publication_slug, email, mobile, plan_price):
    User = get_user_model()
    user = User.objects.create_user(username=username, email=email, password=password)
    acquisition = CustomerAcquisition.objects.create(
        user=user,
        plan_price=plan_price,
        business_name=business_name,
        publication_name=publication_name,
        publication_slug=publication_slug,
        email=email,
        mobile=mobile,
        status=CustomerAcquisition.Status.PAYMENT_PENDING,
    )
    mapping = get_active_mapping(plan_price, settings.RAZORPAY_ENVIRONMENT)
    checkout = {
        'acquisition_id': acquisition.id,
        'plan_id': plan_price.plan_id,
        'billing_cycle': plan_price.billing_cycle,
        'amount': plan_price.amount,
        'currency': plan_price.currency,
        'razorpay_plan_id': mapping.razorpay_plan_id,
        'environment': settings.RAZORPAY_ENVIRONMENT,
    }
    return acquisition, checkout


@transaction.atomic
def create_tenant_after_verified_subscription(*, acquisition, provider_subscription_id):
    acquisition = CustomerAcquisition.objects.select_for_update().select_related('user', 'plan_price__plan').get(pk=acquisition.pk)
    if acquisition.tenant_id:
        return acquisition.tenant

    tenant, _ = Tenant.objects.get_or_create(
        slug=acquisition.publication_slug,
        defaults={
            'owner': acquisition.user,
            'business_name': acquisition.business_name,
            'publication_name': acquisition.publication_name,
            'status': Tenant.Status.TRIAL,
            'onboarding_status': Tenant.OnboardingStatus.IN_PROGRESS,
            'email': acquisition.email,
            'mobile': acquisition.mobile,
        },
    )
    TenantMembership.objects.get_or_create(
        tenant=tenant,
        user=acquisition.user,
        defaults={
            'role': TenantMembership.Role.OWNER,
            'status': TenantMembership.Status.ACTIVE,
            'joined_at': timezone.now(),
        },
    )
    TenantSubscription.objects.update_or_create(
        tenant=tenant,
        defaults={
            'plan': acquisition.plan_price.plan,
            'billing_cycle': acquisition.plan_price.billing_cycle,
            'razorpay_subscription_id': provider_subscription_id,
            'status': TenantSubscription.Status.ACTIVE,
            'start_at': timezone.now(),
            'current_period_start': timezone.now(),
        },
    )
    from .models import TenantOnboarding

    TenantOnboarding.objects.get_or_create(
        tenant=tenant,
        defaults={'status': TenantOnboarding.Status.ONBOARDING},
    )
    acquisition.tenant = tenant
    acquisition.provider_subscription_id = provider_subscription_id
    acquisition.status = CustomerAcquisition.Status.TENANT_CREATED
    acquisition.verified_at = timezone.now()
    acquisition.save(update_fields=['tenant', 'provider_subscription_id', 'status', 'verified_at', 'updated_at'])
    get_effective_entitlements(tenant)
    return tenant


@transaction.atomic
def submit_onboarding_for_review(*, onboarding, actor=None):
    onboarding.status = TenantOnboarding.Status.SUBMITTED_FOR_REVIEW
    onboarding.submitted_at = timezone.now()
    onboarding.save(update_fields=['status', 'submitted_at', 'updated_at'])
    OnboardingReviewEvent.objects.create(
        onboarding=onboarding,
        action=OnboardingReviewEvent.Action.SUBMITTED,
        actor=actor,
    )
    return onboarding


@transaction.atomic
def record_onboarding_review(*, onboarding, action, actor=None, notes=''):
    status_map = {
        OnboardingReviewEvent.Action.UNDER_REVIEW: TenantOnboarding.Status.UNDER_REVIEW,
        OnboardingReviewEvent.Action.CHANGES_REQUESTED: TenantOnboarding.Status.CHANGES_REQUESTED,
        OnboardingReviewEvent.Action.APPROVED: TenantOnboarding.Status.READY_TO_PUBLISH,
        OnboardingReviewEvent.Action.PUBLISHED: TenantOnboarding.Status.PUBLISHED,
        OnboardingReviewEvent.Action.REJECTED: TenantOnboarding.Status.REJECTED,
    }
    onboarding.status = status_map[action]
    onboarding.reviewer_notes = notes
    onboarding.reviewed_at = timezone.now()
    update_fields = ['status', 'reviewer_notes', 'reviewed_at', 'updated_at']
    if action == OnboardingReviewEvent.Action.PUBLISHED:
        onboarding.published_at = timezone.now()
        onboarding.tenant.status = Tenant.Status.ACTIVE
        onboarding.tenant.onboarding_status = Tenant.OnboardingStatus.COMPLETE
        onboarding.tenant.save(update_fields=['status', 'onboarding_status', 'updated_at'])
        update_fields.append('published_at')
    onboarding.save(update_fields=update_fields)
    OnboardingReviewEvent.objects.create(onboarding=onboarding, action=action, actor=actor, notes=notes)
    return onboarding


@transaction.atomic
def request_plan_change(*, tenant, to_plan, requested_by=None, effective_at=None, provider_reference=''):
    subscription = TenantSubscription.objects.select_for_update().select_related('plan').get(tenant=tenant)
    change_type = (
        PlanChangeRequest.ChangeType.UPGRADE
        if to_plan.version >= subscription.plan.version
        else PlanChangeRequest.ChangeType.DOWNGRADE
    )
    return PlanChangeRequest.objects.create(
        tenant=tenant,
        from_plan=subscription.plan,
        to_plan=to_plan,
        requested_by=requested_by,
        change_type=change_type,
        effective_at=effective_at,
        provider_reference=provider_reference,
    )


@transaction.atomic
def apply_verified_plan_change(*, plan_change, provider_reference=''):
    plan_change = PlanChangeRequest.objects.select_for_update().select_related('tenant', 'to_plan').get(pk=plan_change.pk)
    subscription = TenantSubscription.objects.select_for_update().get(tenant=plan_change.tenant)
    subscription.plan = plan_change.to_plan
    subscription.status = TenantSubscription.Status.ACTIVE
    subscription.save(update_fields=['plan', 'status', 'updated_at'])
    plan_change.status = PlanChangeRequest.Status.APPLIED
    plan_change.provider_reference = provider_reference or plan_change.provider_reference
    plan_change.save(update_fields=['status', 'provider_reference', 'updated_at'])
    get_effective_entitlements(plan_change.tenant)
    return subscription


@transaction.atomic
def activate_tenant_add_on(*, tenant_add_on, provider_subscription_id=''):
    tenant_add_on = TenantAddOn.objects.select_for_update().get(pk=tenant_add_on.pk)
    tenant_add_on.provider_subscription_id = provider_subscription_id or tenant_add_on.provider_subscription_id
    tenant_add_on.status = TenantAddOn.Status.ACTIVE
    tenant_add_on.is_active = True
    tenant_add_on.starts_at = tenant_add_on.starts_at or timezone.now()
    tenant_add_on.save(update_fields=['provider_subscription_id', 'status', 'is_active', 'starts_at', 'updated_at'])
    get_effective_entitlements(tenant_add_on.tenant)
    return tenant_add_on


@transaction.atomic
def process_webhook(*, body, signature, environment=None):
    environment = environment or settings.RAZORPAY_ENVIRONMENT
    verify_razorpay_signature(body=body, signature=signature, secret=settings.RAZORPAY_WEBHOOK_SECRET)
    payload = json.loads(body.decode('utf-8'))
    event_id = payload.get('id')
    event_type = payload.get('event')
    if not event_id or not event_type:
        raise ValidationError("Webhook payload missing id or event.")
    event, created = WebhookEvent.objects.get_or_create(
        environment=environment,
        provider='razorpay',
        event_id=event_id,
        defaults={'event_type': event_type, 'payload': payload},
    )
    if not created:
        return event
    event.processed_at = timezone.now()
    event.save(update_fields=['processed_at', 'updated_at'])
    return event
