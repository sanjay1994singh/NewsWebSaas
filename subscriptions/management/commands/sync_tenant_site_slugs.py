from django.core.management.base import BaseCommand
from django.utils.text import slugify

from subscriptions.models import CustomerAcquisition
from tenants.models import Tenant


def _desired_site_slug(tenant):
    return (slugify(tenant.business_name or tenant.publication_name or tenant.slug)[:150].strip('-') or tenant.slug)


def _unique_slug(base_slug, tenant, used_slugs):
    candidate = base_slug
    index = 2
    while candidate in used_slugs or Tenant.objects.exclude(pk=tenant.pk).filter(slug=candidate).exists():
        suffix = f'-{index}'
        candidate = f'{base_slug[:160 - len(suffix)]}{suffix}'
        index += 1
    return candidate


class Command(BaseCommand):
    help = 'Sync tenant public site slugs from Channel name / Paper name.'

    def handle(self, *args, **options):
        used_slugs = set(Tenant.objects.values_list('slug', flat=True))
        updated = 0
        for tenant in Tenant.objects.order_by('id'):
            desired_slug = _desired_site_slug(tenant)
            if tenant.slug == desired_slug:
                continue
            used_slugs.discard(tenant.slug)
            new_slug = _unique_slug(desired_slug, tenant, used_slugs)
            old_slug = tenant.slug
            tenant.slug = new_slug
            tenant.save(update_fields=['slug', 'updated_at'])
            CustomerAcquisition.objects.filter(tenant=tenant).update(publication_slug=new_slug)
            used_slugs.add(new_slug)
            updated += 1
            self.stdout.write(f'{old_slug} -> {new_slug}')
        self.stdout.write(self.style.SUCCESS(f'Synced {updated} tenant site slug(s).'))
