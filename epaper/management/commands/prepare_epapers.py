from django.core.management.base import BaseCommand, CommandError
from epaper.models import EPaperEdition
from epaper.services import mark_epaper_ready


class Command(BaseCommand):
    help = 'Prepare optimized reader pages for existing editions that have no page images.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Limit to a tenant slug.')
        parser.add_argument('--retry-failed', action='store_true')
        parser.add_argument('--watch', action='store_true', help='Keep processing newly uploaded editions.')

    def handle(self, *args, **options):
        import time
        from django.db import close_old_connections
        while True:
            close_old_connections()
            failures = self.process_batch(options)
            if not options['watch']:
                if failures:
                    raise CommandError(f'{failures} edition(s) could not be prepared.')
                return
            time.sleep(5)

    def process_batch(self, options):
        queryset = EPaperEdition.objects.filter(pages__isnull=True).exclude(status='archived')
        if options['watch']:
            queryset = queryset.filter(status='processing')
        if not options['retry_failed']:
            queryset = queryset.exclude(status='failed')
        if options['tenant']:
            queryset = queryset.filter(tenant__slug=options['tenant'])
        failures = 0
        for edition in queryset.iterator():
            try:
                result = mark_epaper_ready(edition)
                self.stdout.write(f'{edition.uuid}: {result.page_count} pages ready')
            except Exception as exc:
                failures += 1
                self.stderr.write(f'{edition.uuid}: {exc}')
        return failures
