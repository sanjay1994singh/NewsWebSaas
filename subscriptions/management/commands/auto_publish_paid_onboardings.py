from django.core.management.base import BaseCommand

from subscriptions.services import auto_publish_paid_onboardings


class Command(BaseCommand):
    help = 'Auto-publish paid tenant onboarding records after the configured waiting period.'

    def add_arguments(self, parser):
        parser.add_argument('--minutes', type=int, default=30)
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        published = auto_publish_paid_onboardings(
            older_than_minutes=options['minutes'],
            limit=options['limit'],
        )
        self.stdout.write(self.style.SUCCESS(f'Auto-published {len(published)} onboarding record(s).'))
