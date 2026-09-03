from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from categories.models import Category
from core.models import user_can_access_tenant
from tenants.models import TenantMembership

from .forms import NewsArticleForm
from .models import AuthorProfile
from .models import NewsArticle
from .services import active_breaking_news_for_tenant, search_articles


def _active_tenant_for_user(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        membership = (
            TenantMembership.objects
            .select_related('tenant')
            .filter(user=request.user, status=TenantMembership.Status.ACTIVE)
            .order_by('role', 'created_at')
            .first()
        )
        tenant = membership.tenant if membership else None
    if tenant is None:
        return None
    if not user_can_access_tenant(request.user, tenant):
        raise PermissionDenied("You do not have access to this workspace.")
    return tenant


def _ensure_publishing_defaults(tenant, user):
    Category.objects.get_or_create(
        tenant=tenant,
        slug='general',
        defaults={'name': 'General', 'show_in_menu': True, 'is_active': True},
    )
    AuthorProfile.objects.get_or_create(
        tenant=tenant,
        slug='editor',
        defaults={'user': user, 'display_name': tenant.publication_name or user.get_username()},
    )


@login_required
def article_dashboard(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    articles = (
        NewsArticle.objects
        .for_tenant(tenant)
        .select_related('category', 'author')
        .order_by('-updated_at')[:25]
    )
    stats = {
        'total': NewsArticle.objects.for_tenant(tenant).count(),
        'published': NewsArticle.objects.for_tenant(tenant).filter(status=NewsArticle.Status.PUBLISHED).count(),
        'draft': NewsArticle.objects.for_tenant(tenant).filter(status=NewsArticle.Status.DRAFT).count(),
        'review': NewsArticle.objects.for_tenant(tenant).filter(status=NewsArticle.Status.REVIEW).count(),
    }
    return render(request, 'news/article_dashboard.html', {'tenant': tenant, 'articles': articles, 'stats': stats})


@login_required
def article_create(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    _ensure_publishing_defaults(tenant, request.user)
    form = NewsArticleForm(request.POST or None, request.FILES or None, tenant=tenant)
    form.instance.tenant = tenant
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.tenant = tenant
        article.full_clean()
        article.save()
        form.save_m2m()
        messages.success(request, 'Article saved successfully.')
        return redirect('news:article_dashboard')
    return render(request, 'news/article_form.html', {'tenant': tenant, 'form': form, 'title': 'Add News Article'})


@login_required
def article_detail(request, uuid):
    article = get_object_or_404(
        NewsArticle.objects.select_related('tenant', 'category', 'author'),
        uuid=uuid,
    )
    if not user_can_access_tenant(request.user, article.tenant):
        raise PermissionDenied("You do not have access to this article.")
    return render(request, 'news/article_detail.html', {'article': article})


@login_required
def article_update(request, uuid):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    article = get_object_or_404(
        NewsArticle.objects.for_tenant(tenant).select_related('tenant', 'category', 'author'),
        uuid=uuid,
    )
    form = NewsArticleForm(request.POST or None, request.FILES or None, instance=article, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.tenant = tenant
        article.full_clean()
        article.save()
        form.save_m2m()
        messages.success(request, 'Article updated successfully.')
        return redirect('news:article_dashboard')
    return render(request, 'news/article_form.html', {'tenant': tenant, 'form': form, 'article': article, 'title': 'Edit News Article'})


@login_required
def article_delete(request, uuid):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    article = get_object_or_404(NewsArticle.objects.for_tenant(tenant), uuid=uuid)
    if request.method == 'POST':
        article.delete()
        messages.success(request, 'Article deleted successfully.')
        return redirect('news:article_dashboard')
    return render(request, 'news/article_confirm_delete.html', {'tenant': tenant, 'article': article})


@login_required
def tenant_article_search(request):
    articles = search_articles(tenant=request.tenant, query=request.GET.get('q'))
    return JsonResponse({
        'results': [
            {'uuid': str(article.uuid), 'title': article.title, 'slug': article.slug}
            for article in articles[:25]
        ]
    })


@login_required
def tenant_breaking_news(request):
    items = active_breaking_news_for_tenant(request.tenant)
    return JsonResponse({
        'results': [
            {'title': item.title, 'article_uuid': str(item.article.uuid)}
            for item in items[:25]
        ]
    })
