from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import user_can_access_tenant
from categories.models import Category
from domains.forms import PrimaryDomainSelectionForm
from domains.middleware import TenantResolutionMiddleware
from domains.models import TenantDomain
from news.models import AuthorProfile, NewsArticle
from subscriptions.models import Plan, TenantOnboarding, TenantSubscription
from subscriptions.services import ensure_required_tenant_pages, tenant_public_site_slug, tenant_public_site_url

from .models import Tenant, TenantMembership, TenantVisitor


@override_settings(ALLOWED_HOSTS=['testserver', 'customera.platformdomain.com', 'www.customera.platformdomain.com', 'customerb.platformdomain.com', 'newdomain.platformdomain.com', 'unknown.platformdomain.com'])
class TenantIsolationTests(TestCase):
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
        self.domain_a = TenantDomain.objects.create(
            tenant=self.tenant_a,
            domain='CustomerA.PlatformDomain.com.',
            domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN,
            is_primary=True,
            is_verified=True,
        )
        self.domain_b = TenantDomain.objects.create(
            tenant=self.tenant_b,
            domain='customerb.platformdomain.com',
            domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN,
            is_primary=True,
            is_verified=True,
        )

    def test_queryset_can_be_scoped_to_tenant(self):
        domains = TenantDomain.objects.for_tenant(self.tenant_a)
        self.assertIn(self.domain_a, domains)
        self.assertNotIn(self.domain_b, domains)

    def test_direct_url_blocks_cross_tenant_idor(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('tenants:tenant_settings', args=[self.tenant_b.uuid]))
        self.assertEqual(response.status_code, 403)

    def test_api_blocks_cross_tenant_access(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('api:tenant_summary', args=[self.tenant_b.uuid]))
        self.assertEqual(response.status_code, 403)

    @override_settings(SITE_BASE_URL='https://pressnexa.live-app.in')
    def test_dashboard_on_foreign_tenant_domain_redirects_to_main_account_area(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('tenants:tenant_dashboard'), HTTP_HOST='customerb.platformdomain.com')
        self.assertRedirects(response, 'https://pressnexa.live-app.in/dashboard/', fetch_redirect_response=False)

    def test_permission_helper_allows_only_active_membership(self):
        self.assertTrue(user_can_access_tenant(self.user_a, self.tenant_a))
        self.assertFalse(user_can_access_tenant(self.user_a, self.tenant_b))

    def test_dashboard_domain_feature_links_to_domain_settings(self):
        plan = Plan.objects.create(
            name='Domain Plan',
            code=Plan.Code.NEWS_STARTER,
            entitlements={'custom_domain': True},
        )
        TenantSubscription.objects.create(
            tenant=self.tenant_a,
            plan=plan,
            status=TenantSubscription.Status.ACTIVE,
            billing_cycle='monthly',
        )
        self.client.force_login(self.user_a)

        response = self.client.get(reverse('tenants:tenant_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Domain Setup')
        self.assertContains(response, reverse('domains:domain_list'))
        self.assertNotContains(response, '/dashboard/domains/')

    def test_tenant_scoped_form_rejects_foreign_domain(self):
        form = PrimaryDomainSelectionForm(
            data={'domain': self.domain_b.pk},
            tenant=self.tenant_a,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('domain', form.errors)

    def test_middleware_normalizes_host_and_attaches_tenant(self):
        factory = RequestFactory()
        request = factory.get('/', HTTP_HOST='WWW.CUSTOMERA.PLATFORMDOMAIN.COM:443')
        TenantResolutionMiddleware(lambda req: None)(request)
        self.assertEqual(request.tenant, self.tenant_a)

    def test_unknown_domain_does_not_attach_any_tenant(self):
        factory = RequestFactory()
        request = factory.get('/', HTTP_HOST='unknown.platformdomain.com')
        TenantResolutionMiddleware(lambda req: None)(request)
        self.assertIsNone(request.tenant)

    def test_public_site_path_opens_without_custom_ssl_domain(self):
        response = self.client.get(reverse('tenants:public_tenant_site', args=[tenant_public_site_slug(self.tenant_a)]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.tenant_a.business_name)

    def test_tenant_domain_root_opens_public_site(self):
        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.tenant_a.business_name)
        self.assertNotContains(response, 'A News brings you')
        self.assertContains(response, 'Account')
        self.assertContains(response, '/account/login/?next=/dashboard/')
        self.assertNotContains(response, 'Latest updates')
        self.assertNotContains(response, 'href="/videos/"')
        self.assertNotContains(response, 'href="/live-tv/"')
        self.assertNotContains(response, 'href="/latest-news/"')
        self.assertNotContains(response, 'href="/top-stories/"')
        self.assertNotContains(response, 'data-block-type="videos"')
        self.assertNotContains(response, 'data-block-type="live_tv"')
        self.assertNotContains(response, 'Video and Live TV sections available')
        self.assertNotContains(response, '<strong>Videos</strong>', html=True)
        self.assertNotContains(response, '<strong>Live TV</strong>', html=True)
        self.assertNotContains(response, 'Launch Your Digital News Platform')

    def test_required_public_pages_open_from_tenant_domain_and_footer(self):
        ensure_required_tenant_pages(tenant=self.tenant_a)

        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/about-us/"')
        self.assertContains(response, 'href="/privacy-policy/"')
        self.assertContains(response, 'Editorial Policy')

        page_response = self.client.get('/privacy-policy/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, 'Privacy Policy')
        self.assertContains(page_response, 'A News')

    def test_public_nav_shows_home_and_tenant_categories(self):
        Category.objects.create(tenant=self.tenant_a, name='Local News', slug='local-news', show_in_menu=True, menu_order=1)
        Category.objects.create(tenant=self.tenant_a, name='Hidden', slug='hidden', show_in_menu=False, menu_order=2)

        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/category/local-news/"')
        self.assertNotContains(response, 'href="/category/hidden/"')
        self.assertNotContains(response, 'href="/latest-news/"')
        self.assertNotContains(response, 'href="/top-stories/"')

    def test_public_category_page_filters_articles(self):
        category = Category.objects.create(tenant=self.tenant_a, name='Local News', slug='local-news', show_in_menu=True)
        other_category = Category.objects.create(tenant=self.tenant_a, name='Sports', slug='sports', show_in_menu=True)
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Local category story',
            slug='local-category-story',
            content='<p>Body</p>',
            status=NewsArticle.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=other_category,
            author=author,
            title='Sports story',
            slug='sports-story',
            content='<p>Body</p>',
            status=NewsArticle.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        response = self.client.get('/category/local-news/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Local category story')
        self.assertNotContains(response, 'Sports story')

    def test_required_public_pages_open_from_platform_site_path(self):
        ensure_required_tenant_pages(tenant=self.tenant_a)

        response = self.client.get(reverse('tenants:public_tenant_page', args=[tenant_public_site_slug(self.tenant_a), 'about-us']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'About Us')
        self.assertContains(response, 'A News')

    def test_disabled_video_and_live_tv_public_pages_return_404(self):
        response = self.client.get('/videos/', HTTP_HOST='customera.platformdomain.com')
        self.assertEqual(response.status_code, 404)
        response = self.client.get('/live-tv/', HTTP_HOST='customera.platformdomain.com')
        self.assertEqual(response.status_code, 404)

    def test_tenant_domain_account_menu_shows_dashboard_and_logout_for_logged_in_owner(self):
        self.client.force_login(self.user_a)
        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Account')
        self.assertContains(response, '/dashboard/')
        self.assertContains(response, 'https://wa.me/918279408396')
        self.assertContains(response, 'Help')
        self.assertContains(response, 'Logout')

    def test_tenant_domain_account_menu_hides_dashboard_help_and_chat_for_visitor(self):
        User = get_user_model()
        visitor_user = User.objects.create_user(username='reader', password='testpass123')
        TenantVisitor.objects.create(
            tenant=self.tenant_a,
            user=visitor_user,
            name='Reader',
            email='reader@example.com',
            is_active=True,
        )
        self.client.force_login(visitor_user)

        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/account/profile/')
        self.assertContains(response, 'Logout')
        self.assertNotContains(response, '/dashboard/')
        self.assertNotContains(response, 'https://wa.me/918279408396')
        self.assertNotContains(response, 'Help')

    def test_tenant_domain_account_menu_shows_login_and_register_for_guest(self):
        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/account/login/?next=/dashboard/')
        self.assertContains(response, '/register/')
        self.assertNotContains(response, 'https://wa.me/918279408396')

    def test_tenant_domain_homepage_does_not_show_article_publisher_name(self):
        category = Category.objects.create(tenant=self.tenant_a, name='Local', slug='local')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Local update',
            slug='local-update',
            content='<p>Body</p>',
            featured_image='articles/local.jpg',
            status=NewsArticle.Status.PUBLISHED,
        )

        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Local update')
        article = NewsArticle.objects.get(slug='local-update')
        self.assertContains(response, f'/articles/{article.uuid}/')
        self.assertContains(response, 'src="/media/articles/local.jpg"')
        self.assertContains(response, 'Read full story')
        self.assertContains(response, 'story-card-link')
        self.assertNotContains(response, 'City Desk')
        self.assertNotContains(response, 'By ')

    def test_content_and_reporters_survive_primary_domain_change(self):
        reporter = get_user_model().objects.create_user(username='field-reporter', password='testpass123')
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=reporter,
            role=TenantMembership.Role.REPORTER,
            status=TenantMembership.Status.ACTIVE,
            joined_at=timezone.now(),
        )
        category = Category.objects.create(tenant=self.tenant_a, name='Local', slug='local')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        article = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Domain independent story',
            slug='domain-independent-story',
            content='<p>Body</p>',
            status=NewsArticle.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.domain_a.is_primary = False
        self.domain_a.save(update_fields=['is_primary', 'updated_at'])
        TenantDomain.objects.create(
            tenant=self.tenant_a,
            domain='newdomain.platformdomain.com',
            domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN,
            is_primary=True,
            is_verified=True,
            status=TenantDomain.Status.ACTIVE,
        )

        response = self.client.get(f'/articles/{article.uuid}/', HTTP_HOST='newdomain.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Domain independent story')
        self.assertTrue(TenantMembership.objects.filter(tenant=self.tenant_a, user=reporter, role=TenantMembership.Role.REPORTER).exists())
        self.assertTrue(NewsArticle.objects.filter(tenant=self.tenant_a, title='Domain independent story').exists())

    def test_tenant_domain_homepage_uses_most_viewed_article_as_top_story(self):
        category = Category.objects.create(tenant=self.tenant_a, name='Local', slug='local')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Fresh latest update',
            slug='fresh-latest-update',
            content='<p>Body</p>',
            view_count=2,
            status=NewsArticle.Status.PUBLISHED,
        )
        popular = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Most read report',
            slug='most-read-report',
            short_description='Popular story summary',
            content='<p>Body</p>',
            featured_image='articles/popular.jpg',
            view_count=25,
            status=NewsArticle.Status.PUBLISHED,
        )

        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Most Viewed')
        self.assertContains(response, f'/articles/{popular.uuid}/')
        self.assertContains(response, 'src="/media/articles/popular.jpg"')

    def test_tenant_domain_homepage_contact_section_uses_tenant_details(self):
        TenantOnboarding.objects.create(
            tenant=self.tenant_a,
            status=TenantOnboarding.Status.PUBLISHED,
            address='101 News Street, Delhi',
            facebook_url='https://facebook.example/a-news',
        )

        response = self.client.get('/contact/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Contact A Media')
        self.assertContains(response, 'a@example.com')
        self.assertContains(response, '101 News Street, Delhi')
        self.assertContains(response, 'https://facebook.example/a-news')

    def test_tenant_domain_public_article_detail_can_be_read_and_shared(self):
        category = Category.objects.create(tenant=self.tenant_a, name='Local', slug='local')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        article = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Shareable local update',
            slug='shareable-local-update',
            short_description='Important reader summary',
            content='<p>Full story body</p>',
            featured_image='articles/shareable.jpg',
            status=NewsArticle.Status.PUBLISHED,
        )

        response = self.client.get(f'/articles/{article.uuid}/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Shareable local update')
        self.assertContains(response, 'Full story body')
        self.assertContains(response, 'Share this story')
        self.assertContains(response, 'WhatsApp')
        self.assertContains(response, 'Facebook')
        self.assertContains(response, 'Copy Link')
        self.assertContains(response, f'https://customera.platformdomain.com/articles/{article.uuid}/')
        self.assertContains(response, 'property="og:image"')
        self.assertContains(response, 'https://customera.platformdomain.com/media/articles/shareable.jpg')
        self.assertContains(response, 'name="robots"')
        self.assertContains(response, 'property="og:site_name"')
        self.assertContains(response, 'City Desk')
        content = response.content.decode()
        self.assertLess(content.index('Share this story'), content.index('Full story body'))

    def test_article_view_count_tracks_one_unique_view_per_visitor(self):
        category = Category.objects.create(tenant=self.tenant_a, name='Local', slug='local')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        article = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Tracked update',
            slug='tracked-update',
            content='<p>Body</p>',
            status=NewsArticle.Status.PUBLISHED,
        )
        path = f'/articles/{article.uuid}/'

        first = self.client.get(path, HTTP_HOST='customera.platformdomain.com', HTTP_USER_AGENT='reader-browser')
        second = self.client.get(path, HTTP_HOST='customera.platformdomain.com', HTTP_USER_AGENT='reader-browser')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        article.refresh_from_db()
        self.assertEqual(article.view_count, 1)
        self.assertEqual(article.page_views.count(), 1)

    def test_tenant_domain_slug_article_url_redirects_to_news_id_url(self):
        category = Category.objects.create(tenant=self.tenant_a, name='Local', slug='local')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        article = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Old slug link',
            slug='old-slug-link',
            content='<p>Body</p>',
            status=NewsArticle.Status.PUBLISHED,
        )

        response = self.client.get(f'/articles/{article.slug}/', HTTP_HOST='customera.platformdomain.com')

        self.assertRedirects(response, f'/articles/{article.uuid}/', status_code=301, fetch_redirect_response=False)

    def test_tenant_domain_public_article_detail_hides_unpublished_articles(self):
        category = Category.objects.create(tenant=self.tenant_a, name='Local', slug='local')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='City Desk', slug='city-desk')
        article = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=category,
            author=author,
            title='Draft update',
            slug='draft-update',
            content='<p>Draft story body</p>',
            status=NewsArticle.Status.DRAFT,
        )

        response = self.client.get(f'/articles/{article.uuid}/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 404)

    @override_settings(SITE_BASE_URL='https://pressnexa.live-app.in')
    def test_tenant_domain_admin_redirects_to_main_account_area(self):
        response = self.client.get('/admin/', HTTP_HOST='customera.platformdomain.com')
        self.assertRedirects(response, 'https://pressnexa.live-app.in/dashboard/', fetch_redirect_response=False)

    def test_tenant_domain_login_uses_tenant_branding(self):
        response = self.client.get('/account/login/?next=/dashboard/', HTTP_HOST='customera.platformdomain.com')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A Media')
        self.assertNotContains(response, 'Press Nexa')
        self.assertContains(response, 'Back to website')

    @override_settings(SITE_BASE_URL='https://pressnexa.live-app.in')
    def test_tenant_domain_login_rejects_user_from_other_tenant(self):
        response = self.client.post(
            '/account/login/?next=/dashboard/',
            {'username': 'owner-b', 'password': 'testpass123'},
            HTTP_HOST='customera.platformdomain.com',
            follow=True,
        )

        self.assertRedirects(response, '/account/login/?next=/dashboard/')
        self.assertContains(response, 'Aapka account is site par registered nahi hai')

    @override_settings(SITE_BASE_URL='https://pressnexa.live-app.in')
    def test_tenant_domain_login_shows_registration_link(self):
        response = self.client.get('/account/login/?next=/dashboard/', HTTP_HOST='customera.platformdomain.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register as visitor')
        self.assertContains(response, '/register/')

    def test_tenant_domain_visitor_register_creates_visitor_without_membership(self):
        response = self.client.post(
            '/register/',
            {
                'name': 'Reader One',
                'email': 'reader@example.com',
                'mobile': '9876543210',
                'password': 'testpass123',
                'confirm_password': 'testpass123',
            },
            HTTP_HOST='customera.platformdomain.com',
            follow=True,
        )

        self.assertContains(response, 'Visitor account registered')
        visitor = TenantVisitor.objects.get(email='reader@example.com')
        self.assertEqual(visitor.tenant, self.tenant_a)
        self.assertFalse(TenantMembership.objects.filter(tenant=self.tenant_a, user=visitor.user).exists())

    def test_owner_can_create_reporter_membership(self):
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse('tenants:reporter_create'),
            {
                'full_name': 'Field Reporter',
                'email': 'field@example.com',
                'mobile': '9999999999',
                'password': 'testpass123',
                'confirm_password': 'testpass123',
                'role': TenantMembership.Role.REPORTER,
            },
            follow=True,
        )

        self.assertContains(response, 'Reporter account created')
        membership = TenantMembership.objects.get(user__email='field@example.com', tenant=self.tenant_a)
        self.assertEqual(membership.role, TenantMembership.Role.REPORTER)
        self.assertEqual(membership.status, TenantMembership.Status.ACTIVE)

    def test_tenant_domain_platform_pages_redirect_to_tenant_home(self):
        response = self.client.get('/about-us/', HTTP_HOST='customera.platformdomain.com')
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_main_domain_admin_is_not_redirected_by_tenant_guard(self):
        response = self.client.get('/admin/', HTTP_HOST='testserver')
        self.assertNotEqual(response.url if response.status_code in {301, 302} else '', '/dashboard/')

    @override_settings(SITE_BASE_URL='https://pressnexa.live-app.in')
    def test_public_site_url_uses_channel_or_paper_name(self):
        self.domain_a.is_primary = False
        self.domain_a.save(update_fields=['is_primary', 'updated_at'])
        self.assertEqual(tenant_public_site_url(self.tenant_a), 'https://pressnexa.live-app.in/site/a-media/')

    @override_settings(SITE_BASE_URL='https://pressnexa.live-app.in')
    def test_public_site_url_prefers_primary_domain(self):
        self.domain_a.is_primary = True
        self.domain_a.save(update_fields=['is_primary', 'updated_at'])
        self.assertEqual(tenant_public_site_url(self.tenant_a), 'https://customera.platformdomain.com/')
