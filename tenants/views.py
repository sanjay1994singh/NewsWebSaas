from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from datetime import timedelta

from analytics.services import record_article_view
from core.models import user_can_access_tenant
from categories.models import Category
from domains.models import TenantDomain
from news.models import NewsArticle
from news.services import article_public_path, published_articles_for_tenant
from pages.builder import get_or_create_layout
from pages.models import HomepageBlock, HomepageLayout, Menu, Page
from seo.services import article_json_ld, article_meta
from subscriptions.entitlements import get_effective_entitlements
from subscriptions.models import CustomerAcquisition, TenantOnboarding, TenantSubscription
from subscriptions.services import ensure_required_tenant_pages, tenant_public_site_slug, tenant_public_site_url
from videos.youtube import fetch_youtube_channel_shorts, fetch_youtube_channel_videos

from .forms import ReporterCreateForm, TenantSettingsForm, VisitorRegistrationForm
from .models import Tenant, TenantMembership, TenantVisitor


def is_platform_admin(user):
    return user.is_authenticated and (user.is_superuser or user.is_super_admin or user.is_support_admin)


def _group_youtube_items_by_day(items):
    today = timezone.localdate()
    groups = [
        {'key': 'today', 'label': 'Today', 'items': []},
        {'key': 'yesterday', 'label': 'Yesterday', 'items': []},
        {'key': 'week', 'label': 'This Week', 'items': []},
    ]
    lookup = {group['key']: group for group in groups}
    for item in items:
        published_at = parse_datetime(item.get('published') or '')
        if published_at:
            published_date = timezone.localdate(published_at)
            if published_date == today:
                lookup['today']['items'].append(item)
            elif published_date == today - timedelta(days=1):
                lookup['yesterday']['items'].append(item)
            else:
                lookup['week']['items'].append(item)
        else:
            lookup['today']['items'].append(item)
    occupied_groups = sum(1 for group in groups if group['items'])
    if items and occupied_groups < 3 and len(items) >= 3:
        chunk_size = max((len(items) + 2) // 3, 1)
        for index, group in enumerate(groups):
            start = index * chunk_size
            end = start + chunk_size
            group['items'] = items[start:end]
    return groups


def _tenant_for_user(user):
    membership = (
        TenantMembership.objects
        .select_related('tenant')
        .filter(user=user, status=TenantMembership.Status.ACTIVE)
        .order_by('role', 'created_at')
        .first()
    )
    return membership.tenant if membership else Tenant.objects.filter(owner=user).first()


def _user_can_manage_reporters(user, tenant):
    return user_can_access_tenant(user, tenant, roles=[
        TenantMembership.Role.OWNER,
        TenantMembership.Role.ADMINISTRATOR,
    ])


@login_required
@user_passes_test(is_platform_admin)
def saas_admin_dashboard(request):
    tenants = Tenant.objects.select_related('owner').order_by('-created_at')[:50]
    return render(request, 'tenants/saas_admin_dashboard.html', {'tenants': tenants})


@login_required
def tenant_dashboard(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        tenant = _tenant_for_user(request.user)
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
    can_publish_news = bool(entitlements.get('news_articles', {}).get('is_enabled'))
    can_publish_blog = bool(entitlements.get('blog', {}).get('is_enabled'))
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
        ('blog', 'Blog Publishing', '/cms/?type=blog'),
        ('epaper', 'E-Paper', '/dashboard/epaper/'),
        ('youtube_videos', 'Videos', '/cms/videos/'),
        ('youtube_shorts', 'Shorts', '/cms/shorts/'),
        ('live_tv', 'Live TV', '/cms/live-tv/'),
        ('advertisement_manager', 'Advertisements', '/dashboard/ads/'),
        ('analytics', 'Analytics', '/dashboard/analytics/'),
        ('custom_domain', 'Domain Setup', reverse('domains:domain_list')),
        ('multiple_staff', 'Reporters', '/dashboard/reporters/'),
        ('mobile_app', 'Mobile App', '/dashboard/mobile-app/'),
    ]
    visible_menu = [
        {
            'code': code,
            'label': label,
            'url': url,
            'entitlement': entitlements.get(code),
            'source_label': 'Included in plan' if entitlements.get(code, {}).get('source') in {'plan_feature', 'purchased_plan_snapshot'} else 'Custom access',
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
            'can_publish_news': can_publish_news,
            'can_publish_blog': can_publish_blog,
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


def public_tenant_category(request, tenant_slug, category_slug):
    public_tenants = Tenant.objects.select_related('owner').filter(status__in=[Tenant.Status.TRIAL, Tenant.Status.ACTIVE])
    tenant = public_tenants.filter(slug=tenant_slug).first()
    if tenant is None:
        tenant = next((item for item in public_tenants if tenant_public_site_slug(item) == tenant_slug), None)
    if tenant is None:
        raise Http404("Publication site not found.")
    return _render_public_tenant_site(request, tenant, 'category', category_slug=category_slug)


def public_domain_page(request, page):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        raise Http404("Publication site not found.")
    return _render_public_tenant_site(request, tenant, page)


def public_domain_category(request, category_slug):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        raise Http404("Publication site not found.")
    return _render_public_tenant_site(request, tenant, 'category', category_slug=category_slug)


def visitor_register(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        raise Http404("Publication site not found.")
    if request.method == 'POST':
        form = VisitorRegistrationForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            email = form.cleaned_data.get('email') or ''
            mobile = form.cleaned_data.get('mobile') or ''
            base = (email.split('@', 1)[0] if email else f"visitor{mobile[-4:]}").lower() or 'visitor'
            username = base[:140]
            index = 1
            while User.objects.filter(username=username).exists():
                index += 1
                username = f"{base[:135]}{index}"
            user = User.objects.create_user(
                username=username,
                email=email,
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['name'],
            )
            TenantVisitor.objects.create(
                tenant=tenant,
                user=user,
                name=form.cleaned_data['name'],
                email=email,
                mobile=mobile,
            )
            messages.success(request, 'Visitor account registered. This account is for reading and updates only; dashboard access is managed by the publication owner.')
            return redirect('accounts:login')
    else:
        form = VisitorRegistrationForm()
    return render(request, 'tenants/visitor_register.html', {'tenant': tenant, 'form': form})


@login_required
def reporter_list(request):
    tenant = _tenant_for_user(request.user)
    if tenant is None or not _user_can_manage_reporters(request.user, tenant):
        raise PermissionDenied("Only tenant owners or administrators can manage reporters.")
    reporters = (
        TenantMembership.objects
        .select_related('user')
        .filter(tenant=tenant, role__in=[TenantMembership.Role.REPORTER, TenantMembership.Role.EDITOR])
        .order_by('role', 'user__first_name', 'user__username')
    )
    return render(request, 'tenants/reporter_list.html', {'tenant': tenant, 'reporters': reporters})


@login_required
def reporter_create(request):
    tenant = _tenant_for_user(request.user)
    if tenant is None or not _user_can_manage_reporters(request.user, tenant):
        raise PermissionDenied("Only tenant owners or administrators can manage reporters.")
    if request.method == 'POST':
        form = ReporterCreateForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            email = form.cleaned_data['email']
            username_base = email.split('@', 1)[0].lower() or 'reporter'
            username = username_base[:140]
            index = 1
            while User.objects.filter(username=username).exists():
                index += 1
                username = f"{username_base[:135]}{index}"
            full_name = form.cleaned_data['full_name'].strip()
            first_name, _, last_name = full_name.partition(' ')
            user = User.objects.create_user(
                username=username,
                email=email,
                password=form.cleaned_data['password'],
                first_name=first_name,
                last_name=last_name,
            )
            TenantMembership.objects.create(
                tenant=tenant,
                user=user,
                role=form.cleaned_data['role'],
                status=TenantMembership.Status.ACTIVE,
                joined_at=timezone.now(),
            )
            messages.success(request, 'Reporter account created.')
            return redirect('tenants:reporter_list')
    else:
        form = ReporterCreateForm()
    return render(request, 'tenants/reporter_form.html', {'tenant': tenant, 'form': form})


def _render_public_tenant_site(request, tenant, page='home', category_slug=''):
    allowed_pages = {'home', 'latest-news', 'top-stories', 'blogs', 'videos', 'live-tv', 'contact', 'category'}
    ensure_required_tenant_pages(tenant=tenant)
    static_page = None
    active_category = None
    if page not in allowed_pages:
        static_page = Page.objects.filter(tenant=tenant, slug=page, is_published=True).first()
    if page not in allowed_pages and static_page is None:
        raise Http404("Publication page not found.")
    if page == 'category':
        active_category = get_object_or_404(Category, tenant=tenant, slug=category_slug, is_active=True)
    request.tenant = tenant
    entitlements = get_effective_entitlements(tenant)
    has_videos = entitlements.get('youtube_videos', {}).get('is_enabled') or entitlements.get('youtube_shorts', {}).get('is_enabled')
    has_live_tv = entitlements.get('live_tv', {}).get('is_enabled')
    has_blog_access = entitlements.get('blog', {}).get('is_enabled')
    if page == 'videos' and not has_videos:
        raise Http404("Publication page not found.")
    if page == 'live-tv' and not has_live_tv:
        raise Http404("Publication page not found.")
    if page == 'blogs' and not has_blog_access:
        raise Http404("Publication page not found.")
    footer_pages = list(
        Page.objects
        .filter(tenant=tenant, is_published=True, menu_items__menu__location=Menu.Location.FOOTER, menu_items__is_enabled=True)
        .order_by('menu_items__order', 'title')
        .distinct()
    )
    nav_categories = list(
        Category.objects
        .filter(tenant=tenant, is_active=True, show_in_menu=True)
        .order_by('menu_order', 'name')[:30]
    )
    layout = get_or_create_layout(tenant, HomepageLayout.Status.PUBLISHED)
    blocks = list(layout.blocks.filter(is_enabled=True).select_related('category'))
    blocks = [
        block
        for block in blocks
        if not (
            (block.block_type == HomepageBlock.BlockType.VIDEOS and not has_videos)
            or (block.block_type == HomepageBlock.BlockType.LIVE_TV and not has_live_tv)
        )
    ]
    published_queryset = published_articles_for_tenant(tenant)
    article_queryset = published_queryset.filter(content_type=NewsArticle.ContentType.BLOG if page == 'blogs' else NewsArticle.ContentType.NEWS)
    if active_category:
        article_queryset = article_queryset.filter(category=active_category)
    if page == 'top-stories':
        articles = list(article_queryset.order_by('-view_count', '-published_at', '-created_at')[:12])
    else:
        articles = list(article_queryset.order_by('-published_at', '-created_at')[:12])
    latest_source = article_queryset if active_category else published_queryset.filter(content_type=NewsArticle.ContentType.NEWS)
    latest_articles = list(latest_source.order_by('-published_at', '-created_at')[:3])
    has_blogs = has_blog_access and published_queryset.filter(content_type=NewsArticle.ContentType.BLOG).exists()
    top_article = article_queryset.order_by('-view_count', '-published_at', '-created_at').first()
    try:
        onboarding = tenant.commercial_onboarding
    except TenantOnboarding.DoesNotExist:
        onboarding = None
    youtube_videos = []
    youtube_shorts = []
    youtube_video_groups = []
    youtube_short_groups = []
    if page == 'videos' and has_videos and onboarding and onboarding.youtube_channel_url:
        youtube_videos = fetch_youtube_channel_videos(onboarding.youtube_channel_url)
        if entitlements.get('youtube_shorts', {}).get('is_enabled'):
            youtube_shorts = fetch_youtube_channel_shorts(onboarding.youtube_channel_url)
        youtube_video_groups = _group_youtube_items_by_day(youtube_videos)
        youtube_short_groups = _group_youtube_items_by_day(youtube_shorts)
    can_access_dashboard = user_can_access_tenant(request.user, tenant)
    is_registered_visitor = (
        request.user.is_authenticated
        and TenantVisitor.objects.filter(tenant=tenant, user=request.user, is_active=True).exists()
    )
    return render(request, 'themes/theme_classic/homepage.html', {
        'layout': layout,
        'blocks': blocks,
        'articles': articles,
        'latest_articles': latest_articles,
        'top_article': top_article,
        'tenant': tenant,
        'onboarding': onboarding,
        'has_videos': has_videos,
        'has_live_tv': has_live_tv,
        'has_blogs': has_blogs,
        'page': page,
        'static_page': static_page,
        'active_category': active_category,
        'nav_categories': nav_categories,
        'footer_pages': footer_pages,
        'youtube_videos': youtube_videos,
        'youtube_shorts': youtube_shorts,
        'youtube_video_groups': youtube_video_groups,
        'youtube_short_groups': youtube_short_groups,
        'youtube_embed_origin': f'{request.scheme}://{request.get_host()}',
        'public_site_slug': tenant_public_site_slug(tenant),
        'preview': False,
        'can_access_dashboard': can_access_dashboard,
        'is_registered_visitor': is_registered_visitor,
    })


def public_article_detail(request, uuid):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        raise Http404("Article not found.")
    ensure_required_tenant_pages(tenant=tenant)
    article = get_object_or_404(
        published_articles_for_tenant(tenant),
        uuid=uuid,
    )
    entitlements = get_effective_entitlements(tenant)
    if article.content_type == NewsArticle.ContentType.BLOG and not entitlements.get('blog', {}).get('is_enabled'):
        raise Http404("Article not found.")
    meta = article_meta(article)
    if article.featured_image:
        meta['og_image'] = request.build_absolute_uri(article.featured_image.url)
    share_url = request.build_absolute_uri(article_public_path(article))
    share_text = f"{article.title} - {tenant.business_name or tenant.publication_name}"
    footer_pages = list(
        Page.objects
        .filter(tenant=tenant, is_published=True, menu_items__menu__location=Menu.Location.FOOTER, menu_items__is_enabled=True)
        .order_by('menu_items__order', 'title')
        .distinct()
    )
    nav_categories = list(
        Category.objects
        .filter(tenant=tenant, is_active=True, show_in_menu=True)
        .order_by('menu_order', 'name')[:30]
    )
    can_access_dashboard = user_can_access_tenant(request.user, tenant)
    is_registered_visitor = (
        request.user.is_authenticated
        and TenantVisitor.objects.filter(tenant=tenant, user=request.user, is_active=True).exists()
    )
    _, visitor_cookie = record_article_view(request, article)
    response = render(request, 'themes/theme_classic/article_detail.html', {
        'tenant': tenant,
        'article': article,
        'meta': meta,
        'json_ld': article_json_ld(article),
        'share_url': share_url,
        'share_text': share_text,
        'footer_pages': footer_pages,
        'nav_categories': nav_categories,
        'can_access_dashboard': can_access_dashboard,
        'is_registered_visitor': is_registered_visitor,
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
