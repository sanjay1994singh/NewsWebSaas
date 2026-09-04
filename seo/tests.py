import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from categories.models import Category
from domains.models import TenantDomain
from news.models import AuthorProfile, NewsArticle
from tenants.models import Tenant

from .services import article_json_ld, article_meta, seo_audit_article


@override_settings(ALLOWED_HOSTS=['testserver', 'primary.example.com'])
class SEOTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='owner', password='testpass123')
        self.tenant = Tenant.objects.create(
            owner=self.user,
            business_name='SEO Media',
            publication_name='SEO News',
            slug='seo-news',
            email='seo@example.com',
            status=Tenant.Status.ACTIVE,
            default_language='en',
        )
        TenantDomain.objects.create(
            tenant=self.tenant,
            domain='primary.example.com',
            domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN,
            is_verified=True,
            is_primary=True,
            status=TenantDomain.Status.ACTIVE,
        )
        self.category = Category.objects.create(tenant=self.tenant, name='Politics', slug='politics')
        self.author = AuthorProfile.objects.create(tenant=self.tenant, display_name='Jane Reporter', slug='jane')
        self.article = NewsArticle.objects.create(
            tenant=self.tenant,
            category=self.category,
            author=self.author,
            title='Real Headline',
            slug='real-headline',
            short_description='Real summary',
            content='Body',
            status=NewsArticle.Status.PUBLISHED,
            image_alt='News image',
        )

    def test_canonical_uses_primary_domain(self):
        meta = article_meta(self.article)
        self.assertEqual(meta['canonical'], f'https://primary.example.com/articles/{self.article.uuid}/')

    def test_article_json_ld_uses_real_fields(self):
        data = json.loads(article_json_ld(self.article))
        self.assertEqual(data['@type'], 'NewsArticle')
        self.assertEqual(data['headline'], 'Real Headline')
        self.assertEqual(data['author']['name'], 'Jane Reporter')
        self.assertEqual(data['publisher']['name'], 'SEO News')

    def test_seo_audit_reports_recommendations_not_guarantees(self):
        checks = seo_audit_article(self.article)
        self.assertIn('Missing SEO title.', checks)
        self.assertIn('Missing meta description.', checks)

    def test_robots_txt_includes_primary_domain_sitemap(self):
        request_host = 'primary.example.com'
        response = self.client.get(reverse('robots_txt'), HTTP_HOST=request_host)
        self.assertContains(response, 'Sitemap: https://primary.example.com/sitemap.xml')

    def test_sitemap_is_tenant_specific(self):
        response = self.client.get(reverse('sitemap_xml'), HTTP_HOST='primary.example.com')
        self.assertContains(response, f'https://primary.example.com/articles/{self.article.uuid}/')
        self.assertContains(response, '<urlset')

    def test_news_sitemap_includes_publication_data(self):
        response = self.client.get(reverse('news_sitemap_xml'), HTTP_HOST='primary.example.com')
        self.assertContains(response, '<news:name>SEO News</news:name>')
        self.assertContains(response, '<news:title>Real Headline</news:title>')
