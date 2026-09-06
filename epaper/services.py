from django.utils import timezone

from subscriptions.entitlements import tenant_feature_limit, tenant_has_feature

from .models import EPaperEdition


def can_upload_epaper(tenant):
    return tenant_has_feature(tenant, 'epaper')


def tenant_monthly_epaper_limit(tenant):
    return tenant_feature_limit(tenant, 'epaper_editions_per_month')


def current_month_epaper_count(tenant, when=None):
    when = when or timezone.now()
    return EPaperEdition.objects.filter(
        tenant=tenant,
        created_at__year=when.year,
        created_at__month=when.month,
    ).count()


def epaper_limit_reached(tenant):
    limit = tenant_monthly_epaper_limit(tenant)
    if limit is None:
        return False
    return current_month_epaper_count(tenant) >= limit


def mark_epaper_ready(edition):
    """Render once at upload/backfill time, never in a visitor request.

    Publish only complete sets; retain existing pages if a conversion fails.
    Storage names include tenant, edition and a generation UUID for cache safety.
    """
    from io import BytesIO
    from uuid import uuid4
    import pymupdf
    from PIL import Image
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django.db import transaction
    from .models import EPaperPage

    written = []
    try:
        with transaction.atomic():
            current = EPaperEdition.objects.select_for_update().get(pk=edition.pk)
            if current.pages.exists():
                return current
            with current.pdf_file.open('rb') as source:
                data = source.read()
            with pymupdf.open(stream=data, filetype='pdf') as document:
                if document.needs_pass or not 1 <= len(document) <= 100:
                    raise ValueError('Use an unlocked PDF with 1 to 100 pages.')
                generation = uuid4().hex
                pages = []
                for number, page in enumerate(document, 1):
                    rect = page.rect
                    if rect.width <= 0 or rect.height <= 0:
                        raise ValueError('The PDF contains an invalid page size.')
                    scale = min(3000 / rect.width, 4500 / rect.height)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
                    original = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    fields = {}
                    for field, width, quality in [('zoom_image', 3000, 88), ('image', 1800, 84), ('mobile_image', 1000, 82), ('thumbnail', 240, 68)]:
                        image = original.copy()
                        image.thumbnail((width, round(width * original.height / original.width)), Image.Resampling.LANCZOS)
                        output = BytesIO()
                        image.save(output, 'WEBP', quality=quality, method=4)
                        path = f'epaper/pages/{current.tenant_id}/{current.uuid}/{generation}/{number}-{field}.webp'
                        fields[field] = default_storage.save(path, ContentFile(output.getvalue()))
                        written.append(fields[field])
                    pages.append(EPaperPage(edition=current, number=number, width=original.width, height=original.height, **fields))
                EPaperPage.objects.bulk_create(pages)
                current.page_count = len(pages)
                if current.status != EPaperEdition.Status.PUBLISHED:
                    current.status = EPaperEdition.Status.READY
                current.save(update_fields=['page_count', 'status', 'updated_at'])
                return current
    except Exception:
        for path in written:
            default_storage.delete(path)
        EPaperEdition.objects.filter(pk=edition.pk).exclude(status=EPaperEdition.Status.PUBLISHED).update(status=EPaperEdition.Status.FAILED)
        raise
