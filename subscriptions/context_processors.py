from django.urls import reverse
from django.db import DatabaseError, OperationalError, ProgrammingError

from tenants.models import Tenant

from .models import CustomerAcquisition, TenantOnboarding, TenantSubscription


def _customer_tenant_context(user):
    tenant = (
        Tenant.objects
        .filter(memberships__user=user, memberships__status='active')
        .select_related('owner')
        .order_by('memberships__role', 'created_at')
        .first()
    )
    if tenant is None:
        tenant = Tenant.objects.filter(owner=user).select_related('owner').first()
    subscription = None
    onboarding = None
    if tenant:
        try:
            subscription = tenant.subscription
        except TenantSubscription.DoesNotExist:
            subscription = None
        try:
            onboarding = tenant.commercial_onboarding
        except TenantOnboarding.DoesNotExist:
            onboarding = None
    return tenant, subscription, onboarding


def customer_navigation(request):
    user = request.user
    tenant_domain_tenant = getattr(request, 'tenant', None)
    site_brand_name = tenant_domain_tenant.business_name if tenant_domain_tenant else 'Press Nexa'
    is_tenant_domain = tenant_domain_tenant is not None
    fallback_links = [
        {'label': 'Pricing', 'url': reverse('public_saas_landing')},
        {'label': 'Profile', 'url': reverse('accounts:profile') if user.is_authenticated else reverse('accounts:login')},
    ]
    if not user.is_authenticated:
        return {
            'site_brand_name': site_brand_name,
            'is_tenant_domain': is_tenant_domain,
            'customer_nav_stage': 'guest',
            'customer_nav_links': [
                {'label': 'Home', 'url': '/'} if is_tenant_domain else {'label': 'Pricing', 'url': reverse('public_saas_landing')},
                {'label': 'Login', 'url': reverse('accounts:login')},
            ],
        }

    links = []
    stage = 'account'
    try:
        pending_acquisition = (
            CustomerAcquisition.objects
            .filter(user=user, tenant__isnull=True, status=CustomerAcquisition.Status.PAYMENT_PENDING)
            .order_by('-created_at')
            .first()
        )
        tenant, subscription, onboarding = _customer_tenant_context(user)
    except (DatabaseError, OperationalError, ProgrammingError):
        return {
            'site_brand_name': site_brand_name,
            'is_tenant_domain': is_tenant_domain,
            'customer_nav_stage': 'account',
            'customer_nav_links': fallback_links,
        }

    if tenant and subscription and onboarding and onboarding.status == TenantOnboarding.Status.PUBLISHED:
        stage = 'published'
        links.append({'label': 'Dashboard', 'url': reverse('tenants:tenant_dashboard')})
        links.append({'label': 'Billing', 'url': reverse('subscriptions:billing_dashboard')})
    elif tenant and subscription and (onboarding is None or onboarding.status in {
        TenantOnboarding.Status.PAYMENT_PENDING,
        TenantOnboarding.Status.ONBOARDING,
        TenantOnboarding.Status.CHANGES_REQUESTED,
    }):
        stage = 'onboarding'
        links.append({'label': 'Dashboard', 'url': reverse('tenants:tenant_dashboard')})
        links.append({'label': 'Setup', 'url': reverse('subscriptions:onboarding')})
        links.append({'label': 'Billing', 'url': reverse('subscriptions:billing_dashboard')})
    elif tenant and subscription and onboarding.status in {
        TenantOnboarding.Status.SUBMITTED_FOR_REVIEW,
        TenantOnboarding.Status.UNDER_REVIEW,
    }:
        stage = 'review'
        links.append({'label': 'Dashboard', 'url': reverse('tenants:tenant_dashboard')})
        links.append({'label': 'Review Status', 'url': reverse('subscriptions:review_status')})
        links.append({'label': 'Billing', 'url': reverse('subscriptions:billing_dashboard')})
    elif tenant and subscription and onboarding.status in {
        TenantOnboarding.Status.APPROVED,
        TenantOnboarding.Status.READY_TO_PUBLISH,
    }:
        stage = 'ready'
        links.append({'label': 'Dashboard', 'url': reverse('tenants:tenant_dashboard')})
        links.append({'label': 'Publish Status', 'url': reverse('subscriptions:ready_to_publish')})
        links.append({'label': 'Billing', 'url': reverse('subscriptions:billing_dashboard')})
    elif pending_acquisition:
        stage = 'payment_pending'
        links.append({
            'label': 'Continue Payment',
            'url': reverse('subscriptions:checkout', kwargs={'acquisition_id': pending_acquisition.uuid}),
        })
        links.append({'label': 'Pricing', 'url': reverse('public_saas_landing')})
    elif not tenant or not subscription:
        stage = 'choose_plan'
        links.append({'label': 'Choose Plan', 'url': reverse('public_saas_landing')})
        links.append({'label': 'Account Status', 'url': reverse('subscriptions:account_status')})
    else:
        stage = 'account_status'
        links.append({'label': 'Account Status', 'url': reverse('subscriptions:account_status')})
        links.append({'label': 'Billing', 'url': reverse('subscriptions:billing_dashboard')})

    links.append({'label': 'Profile', 'url': reverse('accounts:profile')})
    if user.is_staff:
        links.append({'label': 'Admin', 'url': reverse('admin:index')})

    return {
        'site_brand_name': site_brand_name,
        'is_tenant_domain': is_tenant_domain,
        'customer_nav_stage': stage,
        'customer_nav_links': links,
    }
