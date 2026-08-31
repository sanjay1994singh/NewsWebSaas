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


def mark_epaper_ready(edition, page_count=0):
    edition.page_count = page_count
    edition.status = EPaperEdition.Status.READY
    edition.save(update_fields=['page_count', 'status', 'updated_at'])
    return edition
