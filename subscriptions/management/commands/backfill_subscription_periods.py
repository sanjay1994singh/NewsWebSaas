from django.core.management.base import BaseCommand

from subscriptions.models import TenantSubscription
from subscriptions.services import subscription_period_for_cycle


class Command(BaseCommand):
    help = 'Fill missing subscription period end and charge dates from the billing cycle.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', default='')

    def handle(self, *args, **options):
        queryset = TenantSubscription.objects.select_related('tenant').filter(
            status=TenantSubscription.Status.ACTIVE,
            start_at__isnull=False,
        )
        if options['tenant_slug']:
            queryset = queryset.filter(tenant__slug=options['tenant_slug'])

        updated = 0
        for subscription in queryset:
            period_start = subscription.current_period_start or subscription.start_at
            _, period_end, charge_at = subscription_period_for_cycle(period_start, subscription.billing_cycle)
            update_fields = []
            if not subscription.current_period_start:
                subscription.current_period_start = period_start
                update_fields.append('current_period_start')
            if not subscription.current_period_end:
                subscription.current_period_end = period_end
                update_fields.append('current_period_end')
            if not subscription.charge_at:
                subscription.charge_at = charge_at
                update_fields.append('charge_at')
            if update_fields:
                subscription.save(update_fields=update_fields + ['updated_at'])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'Backfilled {updated} subscription period(s).'))
