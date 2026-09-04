from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from core.models import user_can_access_tenant
from domains.models import TenantDomain
from news.models import NewsArticle
from pages.builder import get_or_create_layout
from pages.models import HomepageLayout
from subscriptions.entitlements import get_effective_entitlements
from subscriptions.models import CustomerAcquisition, TenantOnboarding, TenantSubscription
from subscriptions.services import tenant_public_site_slug, tenant_public_site_url

from .forms import TenantSettingsForm
from .models import Tenant, TenantMembership


def is_platform_admin(user):
    return user.is_authenticated and (user.is_superuser or user.is_super_admin or user.is_support_admin)


@login_required
@user_passes_test(is_platform_admin)
def saas_admin_dashboard(request):
    tenants = Tenant.objects.select_related('owner').order_by('-created_at')[:50]
    return render(request, 'tenants/saas_admin_dashboard.html', {'tenants': tenants})


@login_required
def tenant_dashboard(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        membership = (
            TenantMembership.objects
            .select_related('tenant')
            .filter(user=request.user, status=TenantMembership.Status.ACTIVE)
            .order_by('role', 'created_at')
            .first()
        )
        tenant = membership.tenant if membership else Tenant.objects.filter(owner=request.user).first()
    if tenant is None:
        pending_acquisition = (
            CustomerAcquisition.objects
            .filter(
                user=request.user,
                tenant__isnull=True,
                status=CustomerAcquisition.Status.PAYMENT_PENDING,
            )
            .order_by('-created_at')
            .first()
        )
        if pending_acquisition:
            messages.info(request, 'Your workspace details are saved. Complete payment to unlock your dashboard.')
            return redirect('subscriptions:checkout', acquisition_id=pending_acquisition.uuid)
        messages.info(request, 'Choose a plan to create your publication workspace before opening the dashboard.')
        return redirect('subscriptions:account_status')
    if not user_can_access_tenant(request.user, tenant):
        raise PermissionDenied("You do not have access to this tenant.")

    try:
        subscription = tenant.subscription
    except TenantSubscription.DoesNotExist:
        subscription = None
    try:
        onboarding = tenant.commercial_onboarding
    except TenantOnboarding.DoesNotExist:
        onboarding = None

    entitlements = get_effective_entitlements(tenant)
    primary_domain = TenantDomain.objects.filter(tenant=tenant, is_primary=True).first()
    site_url = tenant_public_site_url(tenant)
    article_queryset = NewsArticle.objects.filter(tenant=tenant)
    news_stats = {
        'total': article_queryset.count(),
        'published': article_queryset.filter(status=NewsArticle.Status.PUBLISHED).count(),
        'draft': article_queryset.filter(status=NewsArticle.Status.DRAFT).count(),
        'review': article_queryset.filter(status=NewsArticle.Status.REVIEW).count(),
    }
    feature_menu = [
        ('news_articles', 'News Publishing', '/cms/'),
        ('epaper', 'E-Paper', '/dashboard/epaper/'),
        ('youtube_videos', 'Videos', '/cms/videos/'),
        ('youtube_shorts', 'Shorts', '/cms/shorts/'),
        ('live_tv', 'Live TV', '/cms/live-tv/'),
        ('advertisement_manager', 'Advertisements', '/dashboard/ads/'),
        ('analytics', 'Analytics', '/dashboard/analytics/'),
        ('custom_domain', 'Domains', '/dashboard/domains/'),
        ('mobile_app', 'Mobile App', '/dashboard/mobile-app/'),
    ]
    visible_menu = [
        {
            'code': code,
            'label': label,
            'url': url,
            'entitlement': entitlements.get(code),
            'source_label': 'Included in plan' if entitlements.get(code, {}).get('source') == 'plan_feature' else 'Custom access',
        }
        for code, label, url in feature_menu
        if entitlements.get(code, {}).get('is_enabled')
    ]
    return render(
        request,
        'tenants/tenant_dashboard.html',
        {
            'tenant': tenant,
            'subscription': subscription,
            'onboarding': onboarding,
            'entitlements': entitlements,
            'visible_menu': visible_menu,
            'primary_domain': primary_domain,
            'site_url': site_url,
            'news_stats': news_stats,
        },
    )


def public_tenant_site(request, tenant_slug):
    public_tenants = Tenant.objects.select_related('owner').filter(status__in=[Tenant.Status.TRIAL, Tenant.Status.ACTIVE])
    tenant = public_tenants.filter(slug=tenant_slug).first()
    if tenant is None:
        tenant = next((item for item in public_tenants if tenant_public_site_slug(item) == tenant_slug), None)
    if tenant is None:
        raise Http404("Publication site not found.")
    request.tenant = tenant
    layout = get_or_create_layout(tenant, HomepageLayout.Status.PUBLISHED)
    return render(request, 'themes/theme_classic/homepage.html', {
        'layout': layout,
        'blocks': layout.blocks.filter(is_enabled=True).select_related('category'),
        'tenant': tenant,
        'preview': False,
    })


@login_required
def tenant_settings(request, uuid):
    tenant = get_object_or_404(Tenant, uuid=uuid)
    if not user_can_access_tenant(request.user, tenant):
        raise PermissionDenied("You do not have access to this tenant.")
    if request.method == 'POST':
        form = TenantSettingsForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Workspace settings updated.')
            return redirect('tenants:tenant_settings', uuid=tenant.uuid)
    else:
        form = TenantSettingsForm(instance=tenant)
    return render(request, 'tenants/tenant_settings.html', {'tenant': tenant, 'form': form})
