from django.core.management.base import BaseCommand

from tenants.models import Tenant

from subscriptions.services import ensure_platform_domain_for_tenant


class Command(BaseCommand):
    help = 'Create verified primary platform domains for tenants that do not have one.'

    def handle(self, *args, **options):
        created = 0
        for tenant in Tenant.objects.select_related('owner').order_by('id'):
            before = tenant.domains.filter(is_primary=True).first()
            domain = ensure_platform_domain_for_tenant(tenant)
            if before is None:
                created += 1
                self.stdout.write(f'{tenant.slug}: {domain.domain}')
        self.stdout.write(self.style.SUCCESS(f'Ensured platform domains for {created} tenant(s).'))
