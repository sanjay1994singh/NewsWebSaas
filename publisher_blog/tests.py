from datetime import timedelta
from io import StringIO
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from publisher_blog.content import read_article
from publisher_blog.editorial import IST, seed_calendar
from publisher_blog.models import Campaign, Post, word_count
from publisher_blog.views import detail, index, sitemap
from django.http import Http404

@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BlogTests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(starts_on=timezone.localtime(timezone.now(), IST).date())
        self.factory = RequestFactory()

    def ready(self, **kwargs):
        fields = dict(campaign=self.campaign, scheduled_at=timezone.now()-timedelta(minutes=1),
                      language='en', topic='A real guide', slug='test-guide', title='A real guide',
                      description='Useful description', content='<p>'+'word '*950+'</p>', status=Post.Status.READY)
        fields.update(kwargs)
        return Post.objects.create(**fields)

    def test_calendar_idempotent_and_timezone(self):
        self.assertEqual(seed_calendar(self.campaign), 1460)
        self.assertEqual(seed_calendar(self.campaign), 0)
        first = list(self.campaign.posts.all()[:4])
        self.assertEqual([timezone.localtime(p.scheduled_at, IST).hour for p in first], [8,13,17,20])
        self.assertEqual([p.language for p in first], ['hi','en','hi','en'])
        self.assertEqual(timezone.localtime(self.campaign.posts.last().scheduled_at, IST).date(), self.campaign.starts_on+timedelta(days=364))

    def test_publisher_never_exposes_future_or_empty_and_rerun_is_safe(self):
        due = self.ready()
        self.ready(slug='future', scheduled_at=timezone.now()+timedelta(days=1))
        Post.objects.create(campaign=self.campaign, slug='empty', topic='Empty', language='hi', scheduled_at=timezone.now()-timedelta(hours=1))
        call_command('publish_blog', stdout=StringIO())
        due.refresh_from_db()
        stamp = due.published_at
        call_command('publish_blog', stdout=StringIO())
        due.refresh_from_db()
        self.assertEqual(due.published_at, stamp)
        self.assertEqual(Post.objects.filter(status='published').count(), 1)

    def test_paused_and_ended_campaign(self):
        self.ready()
        self.campaign.active = False
        self.campaign.save()
        call_command('publish_blog', stdout=StringIO())
        self.assertFalse(Post.objects.filter(status='published').exists())
        self.campaign.active = True
        self.campaign.starts_on -= timedelta(days=366)
        self.campaign.save()
        call_command('publish_blog', stdout=StringIO())
        self.assertFalse(Post.objects.filter(status='published').exists())

    def test_validation_and_html_safety(self):
        with self.assertRaises(ValidationError):
            self.ready(content='too short')
        post = self.ready(content='<script>alert(1)</script><p>'+'word '*950+'</p>')
        self.assertNotIn('<script>', post.content)

    def test_tenant_isolation_and_visibility(self):
        post = self.ready()
        request = self.factory.get('/blog/')
        request.tenant = object()
        for view, args in ((index, ()), (detail, ('en',post.slug)), (sitemap, ())):
            with self.assertRaises(Http404):
                view(request, *args)
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        request.tenant = None
        with self.assertRaises(Http404):
            detail(request, 'en', post.slug)
        call_command('publish_blog', stdout=StringIO())
        response = detail(request, 'en', post.slug)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BlogPosting', response.content)
        self.assertIn(post.slug.encode(), sitemap(request).content)

    def test_seed_articles_meet_length_and_can_import_twice(self):
        for path in (Path(settings.BASE_DIR)/'content'/'pressnexa').glob('*.md'):
            title, content = read_article(path)
            self.assertTrue(title)
            self.assertGreaterEqual(word_count(content), 900, path.name)
            self.assertLessEqual(word_count(content), 1200, path.name)
        seed_calendar(self.campaign)
        call_command('seed_blog_articles', stdout=StringIO())
        call_command('seed_blog_articles', stdout=StringIO())
        self.assertEqual(Post.objects.filter(status='ready').count(), 4)



    def test_seo_discovery_and_empty_listing(self):
        from django.contrib.auth.models import AnonymousUser
        from seo.views import robots_txt
        request = self.factory.get('/blog/hi/')
        request.tenant = None
        request.user = AnonymousUser()
        self.assertIn((settings.SITE_BASE_URL + '/sitemap.xml').encode(), robots_txt(request).content)
        self.assertIn(b'noindex,follow', index(request, 'hi').content)
        post = self.ready(language='hi')
        call_command('publish_blog', stdout=StringIO())
        response = detail(request, 'hi', post.slug)
        self.assertIn(b'BreadcrumbList', response.content)
        self.assertNotIn(b'noindex,follow', response.content)
        self.assertNotIn(b'noindex,follow', index(request, 'hi').content)

    def test_audit_rejects_a_missing_slot(self):
        from django.core.management.base import CommandError
        seed_calendar(self.campaign)
        call_command('audit_blog_schedule', stdout=StringIO())
        self.campaign.posts.first().delete()
        with self.assertRaises(CommandError):
            call_command('audit_blog_schedule', stdout=StringIO())


    def test_explicit_release_is_visible_before_slot_and_shared_correctly(self):
        from urllib.parse import parse_qs, urlparse
        from publisher_blog.views import reader_meta
        from django.contrib.auth.models import AnonymousUser
        post = self.ready(scheduled_at=timezone.now()+timedelta(days=1), title='News & publishing')
        original_slot = post.scheduled_at
        call_command('release_blog_articles', post.slug, stdout=StringIO())
        post.refresh_from_db()
        self.assertEqual(post.scheduled_at, original_slot)
        request = self.factory.get('/blog/')
        request.tenant = None
        request.user = AnonymousUser()
        response = detail(request, 'en', post.slug)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'copy-link', response.content)
        self.assertIn(b'Facebook', response.content)
        meta = reader_meta(post)
        self.assertEqual(meta.read_minutes, 5)
        self.assertEqual(parse_qs(urlparse(meta.whatsapp_url).query)['text'][0],
                         post.title+'\n'+settings.SITE_BASE_URL+post.get_absolute_url())
        self.assertIn(post.slug.encode(), index(request).content)
        stamp = post.published_at
        call_command('release_blog_articles', post.slug, stdout=StringIO())
        post.refresh_from_db()
        self.assertEqual(post.published_at, stamp)

