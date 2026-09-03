from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import user_can_access_tenant
from tenants.models import TenantMembership

from .models import NewsArticle
from .services import active_breaking_news_for_tenant, search_articles


@login_required
def article_dashboard(request):
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
def article_detail(request, uuid):
    article = get_object_or_404(
        NewsArticle.objects.select_related('tenant', 'category', 'author'),
        uuid=uuid,
    )
    if not user_can_access_tenant(request.user, article.tenant):
        raise PermissionDenied("You do not have access to this article.")
    return render(request, 'news/article_detail.html', {'article': article})


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
