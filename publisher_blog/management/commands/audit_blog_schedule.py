import json
from datetime import datetime, time, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from publisher_blog.editorial import IST, SLOTS
from publisher_blog.models import Campaign, Post, word_count

class Command(BaseCommand):
    help = 'Audit every campaign slot and report actual content readiness, without changing dates.'
    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true')
    def handle(self, *args, **options):
        campaign = Campaign.objects.get(name='Press Nexa 365')
        posts = list(campaign.posts.order_by('scheduled_at'))
        expected = [(datetime.combine(campaign.starts_on + timedelta(days=d), time(hour), IST), language)
                    for d in range(campaign.days) for hour, language in SLOTS]
        actual = [(timezone.localtime(p.scheduled_at, IST), p.language) for p in posts]
        if actual != expected:
            raise CommandError('Calendar mismatch: a slot is missing, duplicated, moved or has the wrong language.')
        invalid = []
        for post in posts:
            if post.status in (Post.Status.READY, Post.Status.PUBLISHED):
                try:
                    post.full_clean()
                except Exception as exc:
                    invalid.append({'slug': post.slug, 'error': type(exc).__name__})
        if invalid:
            raise CommandError(f'Invalid completed articles: {invalid}')
        now = timezone.now()
        report = {
            'campaign': campaign.name, 'active': campaign.active,
            'timezone': 'Asia/Kolkata', 'starts_on': str(campaign.starts_on),
            'ends_on': str(campaign.starts_on + timedelta(days=campaign.days-1)),
            'total_slots': len(posts), 'calendar_valid': True,
            'ready': sum(p.status == Post.Status.READY for p in posts),
            'published': sum(p.status == Post.Status.PUBLISHED for p in posts),
            'awaiting_content': sum(p.status == Post.Status.PENDING for p in posts),
            'overdue_unwritten': sum(p.status == Post.Status.PENDING and p.scheduled_at <= now for p in posts),
        }
        if options['json']:
            report['slots'] = [{'slug': p.slug, 'topic': p.topic, 'language': p.language,
                'scheduled_ist': timezone.localtime(p.scheduled_at, IST).isoformat(),
                'status': p.status, 'words': word_count(p.content)} for p in posts]
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))

