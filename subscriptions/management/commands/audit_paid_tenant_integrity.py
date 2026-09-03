from django.core.management.base import BaseCommand, CommandError

from subscriptions.models import TenantSubscription
from subscriptions.services import ensure_paid_tenant_integrity
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Audit and optionally fix required records for paid tenant workspaces.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', default='')
        parser.add_argument('--fix', action='store_true')

    def handle(self, *args, **options):
        queryset = Tenant.objects.select_related('owner').filter(subscription__status=TenantSubscription.Status.ACTIVE)
        if options['tenant_slug']:
            queryset = queryset.filter(slug=options['tenant_slug'])
        if not queryset.exists():
            raise CommandError('No matching active paid tenant found.')

        total_issues = 0
        for tenant in queryset.order_by('slug'):
            issues = ensure_paid_tenant_integrity(tenant=tenant, fix=options['fix'])
            total_issues += len(issues)
            self.stdout.write(f'{tenant.slug}: {len(issues)} issue(s)')
            for issue in issues:
                status = 'fixed' if issue['fixed'] else 'open'
                self.stdout.write(f"  - [{status}] {issue['code']}: {issue['message']}")

        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS('All checked paid tenants look complete.'))
        elif options['fix']:
            self.stdout.write(self.style.SUCCESS(f'Audit completed with {total_issues} fixed/open issue(s).'))
        else:
            self.stdout.write(self.style.WARNING(f'Audit completed with {total_issues} open issue(s). Run with --fix to apply safe defaults.'))
