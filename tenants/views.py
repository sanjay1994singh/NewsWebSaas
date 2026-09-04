from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from analytics.services import record_article_view
from core.models import user_can_access_tenant
from domains.models import TenantDomain
from news.models import NewsArticle
from news.services import article_public_path, published_articles_for_tenant
from pages.builder import get_or_create_layout
from pages.models import HomepageBlock, HomepageLayout
from seo.services import article_json_ld, article_meta
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
        if getattr(request, 'tenant_domain', None):
            messages.info(request, 'Please open your dashboard from the main Press Nexa account area.')
            return redirect(f"{settings.SITE_BASE_URL}/dashboard/")
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
    return _render_public_tenant_site(request, tenant, 'home')


def public_tenant_page(request, tenant_slug, page):
    public_tenants = Tenant.objects.select_related('owner').filter(status__in=[Tenant.Status.TRIAL, Tenant.Status.ACTIVE])
    tenant = public_tenants.filter(slug=tenant_slug).first()
    if tenant is None:
        tenant = next((item for item in public_tenants if tenant_public_site_slug(item) == tenant_slug), None)
    if tenant is None:
        raise Http404("Publication site not found.")
    return _render_public_tenant_site(request, tenant, page)


def public_domain_page(request, page):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        raise Http404("Publication site not found.")
    return _render_public_tenant_site(request, tenant, page)


def _render_public_tenant_site(request, tenant, page='home'):
    allowed_pages = {'home', 'latest-news', 'top-stories', 'blogs', 'videos', 'live-tv', 'contact'}
    if page not in allowed_pages:
        raise Http404("Publication page not found.")
    request.tenant = tenant
    layout = get_or_create_layout(tenant, HomepageLayout.Status.PUBLISHED)
    blocks = list(layout.blocks.filter(is_enabled=True).select_related('category'))
    published_queryset = published_articles_for_tenant(tenant)
    article_queryset = published_queryset.filter(content_type=NewsArticle.ContentType.BLOG if page == 'blogs' else NewsArticle.ContentType.NEWS)
    if page == 'top-stories':
        articles = list(article_queryset.order_by('-view_count', '-published_at', '-created_at')[:12])
    else:
        articles = list(article_queryset.order_by('-published_at', '-created_at')[:12])
    latest_articles = list(published_queryset.filter(content_type=NewsArticle.ContentType.NEWS).order_by('-published_at', '-created_at')[:3])
    has_blogs = published_queryset.filter(content_type=NewsArticle.ContentType.BLOG).exists()
    top_article = article_queryset.order_by('-view_count', '-published_at', '-created_at').first()
    try:
        onboarding = tenant.commercial_onboarding
    except TenantOnboarding.DoesNotExist:
        onboarding = None
    return render(request, 'themes/theme_classic/homepage.html', {
        'layout': layout,
        'blocks': blocks,
        'articles': articles,
        'latest_articles': latest_articles,
        'top_article': top_article,
        'tenant': tenant,
        'onboarding': onboarding,
        'has_videos': any(block.block_type == HomepageBlock.BlockType.VIDEOS for block in blocks),
        'has_live_tv': any(block.block_type == HomepageBlock.BlockType.LIVE_TV for block in blocks),
        'has_blogs': has_blogs,
        'page': page,
        'public_site_slug': tenant_public_site_slug(tenant),
        'preview': False,
    })


def public_article_detail(request, uuid):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        raise Http404("Article not found.")
    article = get_object_or_404(
        published_articles_for_tenant(tenant),
        uuid=uuid,
    )
    meta = article_meta(article)
    if article.featured_image:
        meta['og_image'] = request.build_absolute_uri(article.featured_image.url)
    share_url = request.build_absolute_uri(article_public_path(article))
    share_text = f"{article.title} - {tenant.business_name or tenant.publication_name}"
    _, visitor_cookie = record_article_view(request, article)
    response = render(request, 'themes/theme_classic/article_detail.html', {
        'tenant': tenant,
        'article': article,
        'meta': meta,
        'json_ld': article_json_ld(article),
        'share_url': share_url,
        'share_text': share_text,
    })
    if visitor_cookie:
        response.set_cookie(
            'pnx_visitor',
            visitor_cookie,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=request.is_secure(),
            samesite='Lax',
        )
    return response


def public_article_slug_redirect(request, slug):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        raise Http404("Article not found.")
    article = get_object_or_404(
        published_articles_for_tenant(tenant),
        slug=slug,
    )
    return redirect(article_public_path(article), permanent=True)


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
