from datetime import datetime, time, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from publisher_blog.editorial import IST
from publisher_blog.models import Post

class Command(BaseCommand):
    help = 'Publish complete due marketing posts. Idempotent; never publishes empty briefs.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        now = timezone.now()
        ids = Post.objects.filter(campaign__active=True, status=Post.Status.READY, scheduled_at__lte=now).values_list('pk', flat=True)
        published = 0
        for pk in list(ids):
            with transaction.atomic():
                post = Post.objects.select_for_update().select_related('campaign').get(pk=pk)
                end = datetime.combine(post.campaign.starts_on + timedelta(days=post.campaign.days), time.min, IST)
                if post.status != Post.Status.READY or not post.campaign.active or now >= end:
                    continue
                post.full_clean()
                if not options['dry_run']:
                    post.status = Post.Status.PUBLISHED
                    post.published_at = now
                    post.save()
                published += 1
        missing = Post.objects.filter(campaign__active=True, status=Post.Status.PENDING, scheduled_at__lte=now).count()
        self.stdout.write(f'{"Would publish" if options["dry_run"] else "Published"}: {published}; overdue empty slots: {missing}')

