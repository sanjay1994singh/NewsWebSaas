from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from core.models import user_can_access_tenant

from .models import NewsArticle
from .services import active_breaking_news_for_tenant, search_articles


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
