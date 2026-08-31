import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.models import user_can_access_tenant

from .builder import (
    add_homepage_block,
    duplicate_homepage_block,
    get_or_create_layout,
    get_or_create_menu,
    publish_homepage_layout,
    restore_default_layout,
    restore_published_to_draft,
    update_homepage_blocks,
)
from .models import HomepageBlock, HomepageLayout, Menu, MenuItem


def _require_tenant_user(request):
    if not user_can_access_tenant(request.user, request.tenant):
        raise PermissionDenied("You do not have access to this tenant.")


@login_required
def homepage_builder(request):
    _require_tenant_user(request)
    layout = get_or_create_layout(request.tenant, HomepageLayout.Status.DRAFT)
    from categories.models import Category

    categories = Category.objects.for_tenant(request.tenant).filter(is_active=True).order_by('name')
    return render(request, 'builder/homepage_builder.html', {
        'layout': layout,
        'blocks': layout.blocks.select_related('category'),
        'categories': categories,
        'block_types': HomepageBlock.BlockType.choices,
    })


@login_required
def homepage_preview(request):
    _require_tenant_user(request)
    status = request.GET.get('status', HomepageLayout.Status.DRAFT)
    layout = get_or_create_layout(request.tenant, status)
    return render(request, 'themes/theme_classic/homepage.html', {
        'layout': layout,
        'blocks': layout.blocks.filter(is_enabled=True).select_related('category'),
        'tenant': request.tenant,
        'preview': status == HomepageLayout.Status.DRAFT,
    })


@login_required
@require_POST
def save_homepage_draft(request):
    _require_tenant_user(request)
    layout = get_or_create_layout(request.tenant, HomepageLayout.Status.DRAFT)
    payload = json.loads(request.body.decode('utf-8') or '[]')
    blocks = update_homepage_blocks(tenant=request.tenant, layout=layout, payload=payload)
    return JsonResponse({'saved': True, 'block_count': blocks.count()})


@login_required
@require_POST
def add_block(request):
    _require_tenant_user(request)
    layout = get_or_create_layout(request.tenant, HomepageLayout.Status.DRAFT)
    block = add_homepage_block(
        tenant=request.tenant,
        layout=layout,
        block_type=request.POST.get('block_type'),
        category_id=request.POST.get('category_id'),
    )
    return redirect('pages:homepage_builder')


@login_required
@require_POST
def remove_block(request, block_id):
    _require_tenant_user(request)
    layout = get_or_create_layout(request.tenant, HomepageLayout.Status.DRAFT)
    deleted, _ = layout.blocks.filter(pk=block_id, tenant=request.tenant).delete()
    if not deleted:
        raise PermissionDenied("Block does not belong to the active tenant.")
    return redirect('pages:homepage_builder')


@login_required
@require_POST
def duplicate_block(request, block_id):
    _require_tenant_user(request)
    layout = get_or_create_layout(request.tenant, HomepageLayout.Status.DRAFT)
    duplicate_homepage_block(tenant=request.tenant, layout=layout, block_id=block_id)
    return redirect('pages:homepage_builder')


@login_required
@require_POST
def publish_homepage(request):
    _require_tenant_user(request)
    publish_homepage_layout(request.tenant)
    return redirect('pages:homepage_builder')


@login_required
@require_POST
def restore_published(request):
    _require_tenant_user(request)
    restore_published_to_draft(request.tenant)
    return redirect('pages:homepage_builder')


@login_required
@require_POST
def restore_default(request):
    _require_tenant_user(request)
    restore_default_layout(request.tenant)
    return redirect('pages:homepage_builder')


@login_required
def menu_builder(request, location='header'):
    _require_tenant_user(request)
    menu = get_or_create_menu(request.tenant, location)
    return render(request, 'builder/menu_builder.html', {
        'menu': menu,
        'items': menu.items.select_related('parent', 'category', 'page'),
        'link_types': MenuItem.LinkType.choices,
    })

# Create your views here.
