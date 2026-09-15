import json
from datetime import date, timedelta
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from publisher_blog.editorial import IST, seed_calendar
from publisher_blog.models import Campaign, Post, word_count

class Command(BaseCommand):
    help = 'Create a 365-day calendar, export pending briefs, or import authored HTML articles.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['init', 'pending', 'import', 'status'])
        parser.add_argument('--start')
        parser.add_argument('--name', default='Press Nexa 365')
        parser.add_argument('--file')
        parser.add_argument('--limit', type=int, default=8)

    def handle(self, *args, **options):
        action = options['action']
        if action == 'init':
            try:
                starts = date.fromisoformat(options['start']) if options['start'] else timezone.localtime(timezone.now(), IST).date() + timedelta(days=1)
            except ValueError as exc:
                raise CommandError('Use YYYY-MM-DD for --start.') from exc
            campaign, created = Campaign.objects.get_or_create(name=options['name'], defaults={'starts_on': starts})
            if not created and options['start'] and campaign.starts_on != starts:
                raise CommandError('Existing start date differs; refusing to reschedule.')
            self.stdout.write(f'{seed_calendar(campaign)} slots created; starts {campaign.starts_on}, {campaign.days} days.')
            return
        try:
            campaign = Campaign.objects.get(name=options['name'])
        except Campaign.DoesNotExist as exc:
            raise CommandError('Run blog_campaign init first.') from exc
        if action == 'status':
            for status, label in Post.Status.choices:
                self.stdout.write(f'{label}: {campaign.posts.filter(status=status).count()}')
        elif action == 'pending':
            rows = list(campaign.posts.filter(status=Post.Status.PENDING).values('slug', 'language', 'topic', 'scheduled_at')[:options['limit']])
            self.stdout.write(json.dumps(rows, ensure_ascii=False, default=str, indent=2))
        else:
            if not options['file']:
                raise CommandError('--file is required.')
            try:
                rows = json.loads(Path(options['file']).read_text(encoding='utf-8-sig'))
                with transaction.atomic():
                    for row in rows:
                        post = campaign.posts.select_for_update().get(slug=row['slug'])
                        if post.status != Post.Status.PENDING:
                            raise CommandError(f'{post.slug} is already written or on hold; refusing overwrite.')
                        post.title = row['title']
                        post.description = row['description']
                        post.content = row['content']
                        post.status = Post.Status.READY
                        post.save()
                        self.stdout.write(f'{post.slug}: {word_count(post.content)} words, ready')
            except (ValueError, KeyError, Post.DoesNotExist) as exc:
                raise CommandError('Invalid import file or unknown slug.') from exc

