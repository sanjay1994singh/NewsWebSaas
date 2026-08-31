from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from categories.models import Category
from domains.models import TenantDomain
from livetv.models import LiveTVChannel
from news.models import AuthorProfile, NewsArticle
from pages.models import Page
from tenants.models import Tenant
from themes.models import TenantBranding
from videos.models import Video


@override_settings(ALLOWED_HOSTS=['testserver', 'a.example.com', 'b.example.com'])
class PublicAPITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(username='owner-a')
        self.user_b = User.objects.create_user(username='owner-b')
        self.tenant_a = Tenant.objects.create(owner=self.user_a, business_name='A', publication_name='A News', slug='a', email='a@example.com', status=Tenant.Status.ACTIVE)
        self.tenant_b = Tenant.objects.create(owner=self.user_b, business_name='B', publication_name='B News', slug='b', email='b@example.com', status=Tenant.Status.ACTIVE)
        TenantDomain.objects.create(tenant=self.tenant_a, domain='a.example.com', domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN, is_verified=True, status=TenantDomain.Status.ACTIVE)
        TenantDomain.objects.create(tenant=self.tenant_b, domain='b.example.com', domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN, is_verified=True, status=TenantDomain.Status.ACTIVE)
        TenantBranding.objects.create(tenant=self.tenant_a, publication_name='A News', primary_color='#111111', secondary_color='#222222', accent_color='#333333')
        self.category_a = Category.objects.create(tenant=self.tenant_a, name='Politics', slug='politics')
        self.category_b = Category.objects.create(tenant=self.tenant_b, name='Secret', slug='secret')
        self.author_a = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='A Author', slug='a-author')
        self.author_b = AuthorProfile.objects.create(tenant=self.tenant_b, display_name='B Author', slug='b-author')
        NewsArticle.objects.create(tenant=self.tenant_a, category=self.category_a, author=self.author_a, title='A Public', slug='a-public', content='A', status=NewsArticle.Status.PUBLISHED)
        NewsArticle.objects.create(tenant=self.tenant_b, category=self.category_b, author=self.author_b, title='B Secret', slug='b-secret', content='B', status=NewsArticle.Status.PUBLISHED)
        Video.objects.create(tenant=self.tenant_a, title='A Video', slug='a-video', source_type=Video.SourceType.YOUTUBE, video_url='https://www.youtube.com/watch?v=abc', status=Video.Status.PUBLISHED)
        LiveTVChannel.objects.create(tenant=self.tenant_a, name='A Live', slug='a-live', source_type=LiveTVChannel.SourceType.HLS, stream_url='https://cdn.example.com/live.m3u8')
        Page.objects.create(tenant=self.tenant_a, title='About', slug='about', content='About A', is_published=True)

    def test_site_config_exposes_safe_public_config(self):
        response = self.client.get(reverse('api:v1_site_config'), HTTP_HOST='a.example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['publication_name'], 'A News')
        self.assertNotIn('firebase', response.content.decode().lower())

    def test_public_tenant_identifier_resolves_mobile_requests(self):
        response = self.client.get(reverse('api:v1_articles'), {'tenant': str(self.tenant_a.uuid)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['title'], 'A Public')

    def test_mismatched_host_and_public_id_is_blocked(self):
        response = self.client.get(reverse('api:v1_articles'), {'tenant': str(self.tenant_b.uuid)}, HTTP_HOST='a.example.com')
        self.assertEqual(response.status_code, 403)

    def test_article_api_never_returns_other_tenant_slug(self):
        response = self.client.get(reverse('api:v1_article_detail', args=['b-secret']), HTTP_HOST='a.example.com')
        self.assertEqual(response.status_code, 404)

    def test_search_videos_livetv_pages_are_tenant_scoped(self):
        self.assertEqual(self.client.get(reverse('api:v1_search'), {'q': 'Secret'}, HTTP_HOST='a.example.com').json()['count'], 0)
        self.assertEqual(self.client.get(reverse('api:v1_videos'), HTTP_HOST='a.example.com').json()['count'], 1)
        self.assertEqual(self.client.get(reverse('api:v1_live_tv'), HTTP_HOST='a.example.com').json()['count'], 1)
        self.assertEqual(self.client.get(reverse('api:v1_pages'), HTTP_HOST='a.example.com').json()['count'], 1)
