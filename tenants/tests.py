from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import user_can_access_tenant
from domains.forms import PrimaryDomainSelectionForm
from domains.middleware import TenantResolutionMiddleware
from domains.models import TenantDomain
from subscriptions.services import tenant_public_site_slug, tenant_public_site_url

from .models import Tenant, TenantMembership


@override_settings(ALLOWED_HOSTS=['testserver', 'customera.platformdomain.com', 'www.customera.platformdomain.com', 'customerb.platformdomain.com', 'unknown.platformdomain.com'])
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

    def test_dashboard_requires_membership_for_resolved_tenant(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('tenants:tenant_dashboard'), HTTP_HOST='customerb.platformdomain.com')
        self.assertEqual(response.status_code, 403)

    def test_permission_helper_allows_only_active_membership(self):
        self.assertTrue(user_can_access_tenant(self.user_a, self.tenant_a))
        self.assertFalse(user_can_access_tenant(self.user_a, self.tenant_b))

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
        self.assertContains(response, self.tenant_a.publication_name)

    def test_tenant_domain_root_opens_public_site(self):
        response = self.client.get('/', HTTP_HOST='customera.platformdomain.com')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.tenant_a.publication_name)
        self.assertNotContains(response, 'Launch Your Digital News Platform')

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
