import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from categories.models import Category

from .models import FooterSection, HomepageBlock, HomepageLayout, Menu, MenuItem, Page


DEFAULT_BLOCKS = [
    (HomepageBlock.BlockType.BREAKING_NEWS, 'Breaking News'),
    (HomepageBlock.BlockType.HERO_NEWS, 'Top Stories'),
    (HomepageBlock.BlockType.LATEST_NEWS, 'Latest News'),
    (HomepageBlock.BlockType.NEWS_GRID, 'News Grid'),
    (HomepageBlock.BlockType.TRENDING, 'Trending'),
    (HomepageBlock.BlockType.EDITOR_PICKS, 'Editor Picks'),
    (HomepageBlock.BlockType.VIDEOS, 'Videos'),
    (HomepageBlock.BlockType.LIVE_TV, 'Live TV'),
]


def get_or_create_layout(tenant, status=HomepageLayout.Status.DRAFT):
    layout, _ = HomepageLayout.objects.get_or_create(tenant=tenant, status=status)
    if not layout.blocks.exists():
        for order, (block_type, heading) in enumerate(DEFAULT_BLOCKS, start=1):
            HomepageBlock.objects.create(
                tenant=tenant,
                layout=layout,
                block_type=block_type,
                heading=heading,
                order=order,
            )
    return layout


def get_or_create_menu(tenant, location=Menu.Location.HEADER):
    return Menu.objects.get_or_create(tenant=tenant, location=location, defaults={'name': location.title()})[0]


def validate_category(tenant, category_id):
    if not category_id:
        return None
    try:
        return Category.objects.for_tenant(tenant).get(pk=category_id)
    except Category.DoesNotExist as exc:
        raise PermissionDenied("Category does not belong to the active tenant.") from exc


def validate_page(tenant, page_id):
    if not page_id:
        return None
    try:
        return Page.objects.for_tenant(tenant).get(pk=page_id)
    except Page.DoesNotExist as exc:
        raise PermissionDenied("Page does not belong to the active tenant.") from exc


@transaction.atomic
def update_homepage_blocks(*, tenant, layout, payload):
    blocks_by_id = {str(block.id): block for block in layout.blocks.select_related('category')}
    seen = set()
    for index, item in enumerate(payload, start=1):
        block_id = str(item.get('id', ''))
        block = blocks_by_id.get(block_id)
        if block is None:
            raise PermissionDenied("Block does not belong to the active tenant.")
        block.category = validate_category(tenant, item.get('category_id'))
        block.heading = item.get('heading', block.heading)[:180]
        block.order = index
        block.is_enabled = bool(item.get('is_enabled', True))
        block.article_count = int(item.get('article_count') or block.article_count)
        block.layout_variant = item.get('layout_variant', block.layout_variant)[:60]
        block.show_image = bool(item.get('show_image', True))
        block.show_description = bool(item.get('show_description', True))
        block.desktop_columns = int(item.get('desktop_columns') or block.desktop_columns)
        block.full_clean()
        block.save()
        seen.add(block.id)
    return layout.blocks.filter(id__in=seen).order_by('order')


@transaction.atomic
def add_homepage_block(*, tenant, layout, block_type, category_id=None):
    allowed = {choice[0] for choice in HomepageBlock.BlockType.choices}
    if block_type not in allowed:
        raise ValidationError("Unsupported block type.")
    order = layout.blocks.count() + 1
    block = HomepageBlock(
        tenant=tenant,
        layout=layout,
        block_type=block_type,
        heading=dict(HomepageBlock.BlockType.choices)[block_type],
        category=validate_category(tenant, category_id),
        order=order,
    )
    block.full_clean()
    block.save()
    return block


@transaction.atomic
def duplicate_homepage_block(*, tenant, layout, block_id):
    block = layout.blocks.get(pk=block_id, tenant=tenant)
    block.pk = None
    block.uuid = uuid.uuid4()
    block.heading = f"{block.heading or block.get_block_type_display()} Copy"
    block.order = layout.blocks.count() + 1
    block.full_clean()
    block.save()
    return block


@transaction.atomic
def publish_homepage_layout(tenant):
    draft = get_or_create_layout(tenant, HomepageLayout.Status.DRAFT)
    published, _ = HomepageLayout.objects.get_or_create(tenant=tenant, status=HomepageLayout.Status.PUBLISHED)
    published.blocks.all().delete()
    published.theme_key = draft.theme_key
    published.published_from = draft
    published.save()
    for draft_block in draft.blocks.order_by('order'):
        draft_block.pk = None
        draft_block.uuid = uuid.uuid4()
        draft_block.layout = published
        draft_block.save()
    return published


@transaction.atomic
def restore_published_to_draft(tenant):
    published = get_or_create_layout(tenant, HomepageLayout.Status.PUBLISHED)
    draft = get_or_create_layout(tenant, HomepageLayout.Status.DRAFT)
    draft.blocks.all().delete()
    for block in published.blocks.order_by('order'):
        block.pk = None
        block.uuid = uuid.uuid4()
        block.layout = draft
        block.save()
    return draft


@transaction.atomic
def restore_default_layout(tenant):
    draft = get_or_create_layout(tenant, HomepageLayout.Status.DRAFT)
    draft.blocks.all().delete()
    for order, (block_type, heading) in enumerate(DEFAULT_BLOCKS, start=1):
        HomepageBlock.objects.create(tenant=tenant, layout=draft, block_type=block_type, heading=heading, order=order)
    return draft
