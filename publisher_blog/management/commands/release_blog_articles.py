from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from publisher_blog.models import Post

class Command(BaseCommand):
    help = 'Explicit editorial release of selected ready articles; preserve calendar slots.'
    def add_arguments(self, parser):
        parser.add_argument('slugs', nargs='+')
    @transaction.atomic
    def handle(self, *args, **options):
        for slug in options['slugs']:
            try:
                post = Post.objects.select_for_update().get(slug=slug)
            except Post.DoesNotExist as exc:
                raise CommandError(f'Unknown article: {slug}') from exc
            if post.status == Post.Status.PUBLISHED:
                self.stdout.write(f'Already published: {slug}')
                continue
            if post.status != Post.Status.READY:
                raise CommandError(f'Article is not ready: {slug}')
            post.status = Post.Status.PUBLISHED
            post.published_at = timezone.now()
            post.save()
            self.stdout.write(f'Published now: {post.get_absolute_url()}')

