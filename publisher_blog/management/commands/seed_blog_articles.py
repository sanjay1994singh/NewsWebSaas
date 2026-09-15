from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from publisher_blog.content import read_article
from publisher_blog.models import Campaign, Post, word_count

SEEDS = [
    ('01-hi-plans.md', 'hi', 'Press Nexa के चारों प्लान, सामग्री सीमा और सही विकल्प चुनने की व्यावहारिक गाइड।'),
    ('02-en-launch.md', 'en', 'Prepare your content, domain, plan and editorial checks for a better organised news website launch.'),
    ('03-hi-future.md', 'hi', 'न्यूज़ वेबसाइट के लिए उपयोगी संभावित सुविधाएँ और उनकी प्राथमिकता तय करने का व्यावहारिक तरीका।'),
    ('04-en-epaper.md', 'en', 'A practical daily ePaper workflow covering edition labels, quality checks, monthly capacity and archives.'),
]

class Command(BaseCommand):
    help = 'Import the four original launch articles into the first four calendar slots; never overwrite.'

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            campaign = Campaign.objects.get(name='Press Nexa 365')
        except Campaign.DoesNotExist as exc:
            raise CommandError('Run blog_campaign init first.') from exc
        posts = list(campaign.posts.select_for_update().order_by('scheduled_at')[:4])
        if len(posts) != 4:
            raise CommandError('Calendar needs four slots.')
        for post, (filename, language, description) in zip(posts, SEEDS):
            if post.status != Post.Status.PENDING:
                self.stdout.write(f'Skipped existing article: {post.slug}')
                continue
            if post.language != language:
                raise CommandError('Unexpected calendar languages.')
            title, content = read_article(Path(settings.BASE_DIR) / 'content' / 'pressnexa' / filename)
            post.title, post.topic, post.content, post.description = title, title, content, description
            post.slug = filename.removesuffix('.md')
            post.status = Post.Status.READY
            post.save()
            self.stdout.write(f'{post.slug}: {word_count(content)} words')

