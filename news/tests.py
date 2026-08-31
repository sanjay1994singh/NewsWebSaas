from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from media_library.models import MediaAsset
from pages.models import Page
from tenants.models import Tenant, TenantMembership

from .forms import NewsArticleForm
from .models import AuthorProfile, BreakingNews, NewsArticle, Tag
from .services import active_breaking_news_for_tenant, search_articles


@override_settings(ALLOWED_HOSTS=['testserver', 'a.example.com', 'b.example.com'])
class TenantNewsCMSTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(username='owner-a', password='testpass123')
        self.user_b = User.objects.create_user(username='owner-b', password='testpass123')
        self.tenant_a = Tenant.objects.create(
            owner=self.user_a,
            business_name='A Media',
            publication_name='A News',
            slug='a-news',
            email='a@example.com',
            status=Tenant.Status.ACTIVE,
        )
        self.tenant_b = Tenant.objects.create(
            owner=self.user_b,
            business_name='B Media',
            publication_name='B News',
            slug='b-news',
            email='b@example.com',
            status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=TenantMembership.Role.OWNER,
            status=TenantMembership.Status.ACTIVE,
            joined_at=timezone.now(),
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role=TenantMembership.Role.OWNER,
            status=TenantMembership.Status.ACTIVE,
            joined_at=timezone.now(),
        )
        self.category_a = Category.objects.create(tenant=self.tenant_a, name='Politics', slug='politics')
        self.category_b = Category.objects.create(tenant=self.tenant_b, name='Politics', slug='politics')
        self.author_a = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='Reporter A', slug='reporter')
        self.author_b = AuthorProfile.objects.create(tenant=self.tenant_b, display_name='Reporter B', slug='reporter')
        self.tag_a = Tag.objects.create(tenant=self.tenant_a, name='Election', slug='election')
        self.tag_b = Tag.objects.create(tenant=self.tenant_b, name='Election', slug='election')
        self.article_a = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=self.category_a,
            author=self.author_a,
            title='Shared headline',
            slug='shared',
            short_description='A tenant story',
            content='<p>Safe</p><script>alert(1)</script>',
            status=NewsArticle.Status.PUBLISHED,
        )
        self.article_b = NewsArticle.objects.create(
            tenant=self.tenant_b,
            category=self.category_b,
            author=self.author_b,
            title='Secret competitor headline',
            slug='shared',
            short_description='B tenant story',
            content='<p>Private</p>',
            status=NewsArticle.Status.PUBLISHED,
        )

    def test_category_slug_uniqueness_is_per_tenant(self):
        self.assertEqual(Category.objects.filter(slug='politics').count(), 2)
        with self.assertRaises(IntegrityError):
            Category.objects.create(tenant=self.tenant_a, name='Politics Duplicate', slug='politics')

    def test_article_slug_uniqueness_is_per_tenant(self):
        self.assertEqual(NewsArticle.objects.filter(slug='shared').count(), 2)
        with self.assertRaises(IntegrityError):
            NewsArticle.objects.create(
                tenant=self.tenant_a,
                category=self.category_a,
                author=self.author_a,
                title='Duplicate',
                slug='shared',
                content='duplicate',
            )

    def test_article_rejects_cross_tenant_category_and_author(self):
        article = NewsArticle(
            tenant=self.tenant_a,
            category=self.category_b,
            author=self.author_b,
            title='Bad boundaries',
            slug='bad-boundaries',
            content='x',
        )
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_article_form_rejects_foreign_category_author_and_tag(self):
        form = NewsArticleForm(
            data={
                'category': self.category_b.pk,
                'author': self.author_b.pk,
                'reporters': [self.author_b.pk],
                'tags': [self.tag_b.pk],
                'title': 'Form attack',
                'slug': 'form-attack',
                'content': 'body',
                'status': NewsArticle.Status.DRAFT,
                'allow_comments': 'on',
                'robots_index': 'on',
                'robots_follow': 'on',
            },
            tenant=self.tenant_a,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)
        self.assertIn('author', form.errors)
        self.assertIn('tags', form.errors)

    def test_search_never_returns_other_tenant_content(self):
        results = list(search_articles(tenant=self.tenant_a, query='competitor'))
        self.assertEqual(results, [])
        results = list(search_articles(tenant=self.tenant_b, query='competitor'))
        self.assertEqual(results, [self.article_b])

    def test_direct_article_url_blocks_cross_tenant_idor(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('news:article_detail', args=[self.article_b.uuid]))
        self.assertEqual(response.status_code, 403)

    def test_unsafe_html_is_sanitized(self):
        self.article_a.refresh_from_db()
        self.assertNotIn('<script', self.article_a.content)
        self.assertIn('<p>Safe</p>', self.article_a.content)

    def test_breaking_news_is_tenant_scoped(self):
        BreakingNews.objects.create(tenant=self.tenant_a, article=self.article_a, title='A breaking', ticker_order=1)
        BreakingNews.objects.create(tenant=self.tenant_b, article=self.article_b, title='B breaking', ticker_order=1)
        titles = [item.title for item in active_breaking_news_for_tenant(self.tenant_a)]
        self.assertEqual(titles, ['A breaking'])

    def test_media_library_is_tenant_scoped(self):
        MediaAsset.objects.create(tenant=self.tenant_a, filename='a.jpg', file='media_library/a.jpg')
        MediaAsset.objects.create(tenant=self.tenant_b, filename='b.jpg', file='media_library/b.jpg')
        self.assertEqual(list(MediaAsset.objects.for_tenant(self.tenant_a).values_list('filename', flat=True)), ['a.jpg'])

    def test_pages_are_tenant_scoped_and_sanitized(self):
        page = Page.objects.create(
            tenant=self.tenant_a,
            title='About Us',
            slug='about',
            page_type=Page.PageType.ABOUT,
            content='<h2>About</h2><iframe src="https://evil.example"></iframe>',
            is_published=True,
        )
        Page.objects.create(
            tenant=self.tenant_b,
            title='About Us',
            slug='about',
            page_type=Page.PageType.ABOUT,
            content='B about',
            is_published=True,
        )
        page.refresh_from_db()
        self.assertNotIn('<iframe', page.content)
        self.assertEqual(Page.objects.for_tenant(self.tenant_a).count(), 1)
