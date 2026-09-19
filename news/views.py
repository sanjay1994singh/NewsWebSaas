import uuid

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from categories.models import Category
from core.models import user_can_access_tenant
from tenants.models import TenantMembership

from .forms import CategoryForm, NewsArticleForm, city_choices_for_location, district_choices_for_location, state_choices_for_country
from .models import AuthorProfile
from .models import NewsArticle, NewsLocation
from .services import active_breaking_news_for_tenant, search_articles, validate_news_article_monthly_limit
from subscriptions.entitlements import get_effective_entitlements
from subscriptions.models import TenantSubscription


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


def _tenant_has_paid_feature(tenant, feature_code):
    try:
        subscription = tenant.subscription
    except TenantSubscription.DoesNotExist:
        return True
    if subscription.status != TenantSubscription.Status.ACTIVE:
        return True
    return bool(get_effective_entitlements(tenant).get(feature_code, {}).get('is_enabled'))


def _ensure_content_type_access(tenant, content_type):
    if content_type == NewsArticle.ContentType.BLOG and not _tenant_has_paid_feature(tenant, 'blog'):
        raise PermissionDenied("Blog publishing is not included in your active plan.")
    if content_type == NewsArticle.ContentType.NEWS and not _tenant_has_paid_feature(tenant, 'news_articles'):
        raise PermissionDenied("News publishing is not included in your active plan.")


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
    _ensure_content_type_access(tenant, content_type)
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
        'can_publish_blog': _tenant_has_paid_feature(tenant, 'blog'),
    })


@login_required
def article_create(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    content_type = request.GET.get('type') or NewsArticle.ContentType.NEWS
    if content_type not in NewsArticle.ContentType.values:
        content_type = NewsArticle.ContentType.NEWS
    _ensure_content_type_access(tenant, content_type)
    _ensure_publishing_defaults(tenant, request.user)
    form = NewsArticleForm(
        request.POST or None,
        request.FILES or None,
        tenant=tenant,
        initial_country=request.session.get('last_article_country', 'India'),
        initial_state=request.session.get('last_article_state', ''),
    )
    form.instance.tenant = tenant
    form.instance.content_type = content_type
    form.fields['content_type'].widget = form.fields['content_type'].hidden_widget()
    form.fields['content_type'].initial = content_type
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.tenant = tenant
        article.content_type = form.cleaned_data.get('content_type') or content_type
        try:
            validate_news_article_monthly_limit(tenant, article)
            article.full_clean()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            article.save()
            form.save_m2m()
            request.session['last_article_country'] = article.country
            request.session['last_article_state'] = article.state
            request.session['last_article_district'] = article.district
            messages.success(request, 'Post saved successfully.')
            return redirect(_article_dashboard_url(article.content_type))
    elif request.method == 'POST':
        messages.error(request, 'Post save nahi hua. Highlighted fields check karke dobara try karein.')
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
    _ensure_content_type_access(article.tenant, article.content_type)
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
    _ensure_content_type_access(tenant, article.content_type)
    form = NewsArticleForm(request.POST or None, request.FILES or None, instance=article, tenant=tenant)
    form.fields['content_type'].widget = form.fields['content_type'].hidden_widget()
    if request.method == 'POST' and form.is_valid():
        article = form.save(commit=False)
        article.tenant = tenant
        try:
            validate_news_article_monthly_limit(tenant, article)
            article.full_clean()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            article.save()
            form.save_m2m()
            request.session['last_article_country'] = article.country
            request.session['last_article_state'] = article.state
            request.session['last_article_district'] = article.district
            messages.success(request, 'Post updated successfully.')
            return redirect(_article_dashboard_url(article.content_type))
    elif request.method == 'POST':
        messages.error(request, 'Post update nahi hua. Highlighted fields check karke dobara try karein.')
    title = 'Edit Blog Post' if article.content_type == NewsArticle.ContentType.BLOG else 'Edit News Article'
    return render(request, 'news/article_form.html', {'tenant': tenant, 'form': form, 'article': article, 'title': title, 'content_type': article.content_type})


@login_required
def article_delete(request, uuid):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return redirect('tenants:tenant_dashboard')
    article = get_object_or_404(NewsArticle.objects.for_tenant(tenant), uuid=uuid)
    _ensure_content_type_access(tenant, article.content_type)
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
@require_POST
def ajax_category_create(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return JsonResponse({'ok': False, 'error': 'Workspace not available.'}, status=403)
    form = CategoryForm(request.POST, tenant=tenant)
    form.instance.tenant = tenant
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
    category = form.save(commit=False)
    category.tenant = tenant
    category.full_clean()
    category.save()
    return JsonResponse({'ok': True, 'id': category.id, 'name': category.name})


@login_required
@require_POST
def ajax_author_create(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return JsonResponse({'ok': False, 'error': 'Workspace not available.'}, status=403)
    display_name = (request.POST.get('display_name') or '').strip()
    if not display_name:
        return JsonResponse({'ok': False, 'errors': {'display_name': ['Author name is required.']}}, status=400)
    base_slug = slugify(display_name)[:160] or f'author-{timezone.now().strftime("%Y%m%d%H%M%S")}'
    slug = base_slug
    counter = 2
    while AuthorProfile.objects.filter(tenant=tenant, slug=slug).exists():
        slug = f'{base_slug[:150]}-{counter}'
        counter += 1
    author = AuthorProfile.objects.create(
        tenant=tenant,
        display_name=display_name,
        slug=slug,
        designation=(request.POST.get('designation') or '').strip(),
        is_public=True,
    )
    return JsonResponse({'ok': True, 'id': author.id, 'name': author.display_name})


def ajax_state_choices(request):
    tenant = _active_tenant_for_user(request) if request.user.is_authenticated else None
    country = request.GET.get('country')
    state = request.GET.get('state')
    district = request.GET.get('district')
    return JsonResponse({
        'states': [{'value': value, 'label': label} for value, label in state_choices_for_country(country)],
        'districts': [{'value': value, 'label': label} for value, label in district_choices_for_location(country, state, tenant=tenant)],
        'cities': [{'value': value, 'label': label} for value, label in city_choices_for_location(country, state, district, tenant=tenant)],
    })


@login_required
@require_POST
def ajax_location_create(request):
    tenant = _active_tenant_for_user(request)
    if tenant is None:
        return JsonResponse({'ok': False, 'error': 'Workspace not available.'}, status=403)
    location_type = (request.POST.get('location_type') or '').strip()
    country = (request.POST.get('country') or 'India').strip()
    state = (request.POST.get('state') or '').strip()
    district = (request.POST.get('district') or '').strip()
    name = (request.POST.get('name') or '').strip()
    if location_type not in {NewsLocation.LocationType.DISTRICT, NewsLocation.LocationType.CITY}:
        return JsonResponse({'ok': False, 'error': 'Invalid location type.'}, status=400)
    if not state:
        return JsonResponse({'ok': False, 'error': 'State select karein.'}, status=400)
    if not name:
        label = 'District' if location_type == NewsLocation.LocationType.DISTRICT else 'City'
        return JsonResponse({'ok': False, 'error': f'{label} name required hai.'}, status=400)
    if location_type == NewsLocation.LocationType.CITY and not district:
        return JsonResponse({'ok': False, 'error': 'City add karne se pehle district select karein.'}, status=400)
    if location_type == NewsLocation.LocationType.DISTRICT:
        district = ''
    location, _ = NewsLocation.objects.get_or_create(
        tenant=tenant,
        location_type=location_type,
        country=country,
        state=state,
        district=district,
        name=name,
    )
    return JsonResponse({'ok': True, 'type': location.location_type, 'name': location.name, 'value': location.name})


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
