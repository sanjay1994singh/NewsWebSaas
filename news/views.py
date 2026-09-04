import uuid

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from categories.models import Category
from core.models import user_can_access_tenant
from tenants.models import TenantMembership

from .forms import CategoryForm, NewsArticleForm
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
        defaults={'user': user, 'display_name': 'Editorial Desk', 'is_public': False},
    )


def _article_dashboard_url(content_type):
    if content_type == NewsArticle.ContentType.BLOG:
        return f"{redirect('news:article_dashboard').url}?type=blog"
    return redirect('news:article_dashboard').url


@login_required
def ckeditor_image_upload(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return JsonResponse({'error': {'message': 'Workspace not available.'}}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': {'message': 'Only image upload is allowed.'}}, status=405)
    upload = request.FILES.get('upload')
    if upload is None:
        return JsonResponse({'error': {'message': 'Please choose an image.'}}, status=400)
    if not (upload.content_type or '').startswith('image/'):
        return JsonResponse({'error': {'message': 'Only image files can be uploaded.'}}, status=400)
    if upload.size > 5 * 1024 * 1024:
        return JsonResponse({'error': {'message': 'Image size must be under 5 MB.'}}, status=400)

    extension = upload.name.rsplit('.', 1)[-1].lower() if '.' in upload.name else 'jpg'
    if extension not in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
        extension = 'jpg'
    path = f'articles/editor/{tenant.id}/{uuid.uuid4().hex}.{extension}'
    saved_path = default_storage.save(path, upload)
    return JsonResponse({'url': default_storage.url(saved_path)})


@login_required
def article_dashboard(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    content_type = request.GET.get('type') or NewsArticle.ContentType.NEWS
    if content_type not in NewsArticle.ContentType.values:
        content_type = NewsArticle.ContentType.NEWS
    articles = (
        NewsArticle.objects
        .for_tenant(tenant)
        .filter(content_type=content_type)
        .select_related('category', 'author')
        .order_by('-updated_at')[:25]
    )
    article_stats = NewsArticle.objects.for_tenant(tenant).filter(content_type=content_type)
    stats = {
        'total': article_stats.count(),
        'published': article_stats.filter(status=NewsArticle.Status.PUBLISHED).count(),
        'draft': article_stats.filter(status=NewsArticle.Status.DRAFT).count(),
        'review': article_stats.filter(status=NewsArticle.Status.REVIEW).count(),
    }
    return render(request, 'news/article_dashboard.html', {
        'tenant': tenant,
        'articles': articles,
        'stats': stats,
        'content_type': content_type,
        'is_blog': content_type == NewsArticle.ContentType.BLOG,
    })


@login_required
def article_create(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    content_type = request.GET.get('type') or NewsArticle.ContentType.NEWS
    if content_type not in NewsArticle.ContentType.values:
        content_type = NewsArticle.ContentType.NEWS
    _ensure_publishing_defaults(tenant, request.user)
    form = NewsArticleForm(request.POST or None, request.FILES or None, tenant=tenant)
    form.instance.tenant = tenant
    form.instance.content_type = content_type
    form.fields['content_type'].widget = form.fields['content_type'].hidden_widget()
    form.fields['content_type'].initial = content_type
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.tenant = tenant
        article.content_type = form.cleaned_data.get('content_type') or content_type
        article.full_clean()
        article.save()
        form.save_m2m()
        messages.success(request, 'Post saved successfully.')
        return redirect(_article_dashboard_url(article.content_type))
    title = 'Add Blog Post' if content_type == NewsArticle.ContentType.BLOG else 'Add News Article'
    return render(request, 'news/article_form.html', {'tenant': tenant, 'form': form, 'title': title, 'content_type': content_type})


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
    form.fields['content_type'].widget = form.fields['content_type'].hidden_widget()
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.tenant = tenant
        article.full_clean()
        article.save()
        form.save_m2m()
        messages.success(request, 'Post updated successfully.')
        return redirect(_article_dashboard_url(article.content_type))
    title = 'Edit Blog Post' if article.content_type == NewsArticle.ContentType.BLOG else 'Edit News Article'
    return render(request, 'news/article_form.html', {'tenant': tenant, 'form': form, 'article': article, 'title': title, 'content_type': article.content_type})


@login_required
def article_delete(request, uuid):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    article = get_object_or_404(NewsArticle.objects.for_tenant(tenant), uuid=uuid)
    if request.method == 'POST':
        article.delete()
        messages.success(request, 'Post deleted successfully.')
        return redirect(_article_dashboard_url(article.content_type))
    return render(request, 'news/article_confirm_delete.html', {'tenant': tenant, 'article': article})


@login_required
def category_list(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    categories = Category.objects.for_tenant(tenant).order_by('menu_order', 'name')
    return render(request, 'news/category_list.html', {'tenant': tenant, 'categories': categories})


@login_required
def category_create(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    form = CategoryForm(request.POST or None, request.FILES or None, tenant=tenant)
    form.instance.tenant = tenant
    if request.method == 'POST' and form.is_valid():
        category = form.save(commit=False)
        category.tenant = tenant
        category.full_clean()
        category.save()
        messages.success(request, 'Category saved successfully.')
        return redirect('news:category_list')
    return render(request, 'news/category_form.html', {'tenant': tenant, 'form': form, 'title': 'Add Category'})


@login_required
def category_update(request, pk):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    category = get_object_or_404(Category.objects.for_tenant(tenant), pk=pk)
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        category = form.save(commit=False)
        category.tenant = tenant
        category.full_clean()
        category.save()
        messages.success(request, 'Category updated successfully.')
        return redirect('news:category_list')
    return render(request, 'news/category_form.html', {'tenant': tenant, 'form': form, 'title': 'Edit Category'})


@login_required
def category_delete(request, pk):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    category = get_object_or_404(Category.objects.for_tenant(tenant), pk=pk)
    if request.method == 'POST':
        try:
            category.delete()
            messages.success(request, 'Category deleted successfully.')
        except ProtectedError:
            messages.error(request, 'This category is used by posts. Move or delete those posts before deleting the category.')
        return redirect('news:category_list')
    return render(request, 'news/category_confirm_delete.html', {'tenant': tenant, 'category': category})


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
