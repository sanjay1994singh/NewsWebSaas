from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tenants.models import Tenant, TenantMembership

from .models import TenantDomain
from .services import create_domain_for_tenant, enqueue_ssl_provisioning, set_primary_domain, verify_domain_ownership
from .validators import validate_public_domain


class DomainValidationTests(TestCase):
    def test_rejects_urls_localhosts_ips_and_invalid_hosts(self):
        invalid = [
            'https://example.com/path',
            'example.com/news',
            'localhost',
            'site.local',
            '127.0.0.1',
            '10.0.0.8',
            'bad_domain',
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_public_domain(value)

    def test_normalizes_www_uppercase_port_and_trailing_dot(self):
        self.assertEqual(validate_public_domain('WWW.Example.COM:443.'), 'example.com')


class DomainWorkflowTests(TestCase):
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
        TenantMembership.objects.create(tenant=self.tenant_a, user=self.user_a, role=TenantMembership.Role.OWNER, status=TenantMembership.Status.ACTIVE, joined_at=timezone.now())
        TenantMembership.objects.create(tenant=self.tenant_b, user=self.user_b, role=TenantMembership.Role.OWNER, status=TenantMembership.Status.ACTIVE, joined_at=timezone.now())

    def test_create_domain_generates_dns_token_and_inactive_status(self):
        domain = create_domain_for_tenant(tenant=self.tenant_a, domain='Example.com')
        self.assertEqual(domain.domain, 'example.com')
        self.assertFalse(domain.is_verified)
        self.assertEqual(domain.status, TenantDomain.Status.INACTIVE)
        self.assertEqual(domain.dns_txt_name, '_infosaas-verify.example.com')
        self.assertIn(domain.verification_token, domain.expected_txt_value)

    def test_duplicate_domain_is_rejected_globally(self):
        create_domain_for_tenant(tenant=self.tenant_a, domain='example.com')
        with self.assertRaises(ValidationError):
            create_domain_for_tenant(tenant=self.tenant_b, domain='www.example.com')

    def test_dns_txt_verification_activates_domain(self):
        domain = create_domain_for_tenant(tenant=self.tenant_a, domain='example.com')
        with patch('domains.services.fetch_dns_txt_values', return_value=[domain.expected_txt_value]):
            verify_domain_ownership(domain)
        domain.refresh_from_db()
        self.assertTrue(domain.is_verified)
        self.assertEqual(domain.status, TenantDomain.Status.ACTIVE)
        self.assertEqual(domain.ssl_status, TenantDomain.SSLStatus.PENDING)

    def test_dns_txt_verification_rejects_missing_token(self):
        domain = create_domain_for_tenant(tenant=self.tenant_a, domain='example.com')
        with patch('domains.services.fetch_dns_txt_values', return_value=['wrong-token']):
            with self.assertRaises(ValidationError):
                verify_domain_ownership(domain)

    def test_primary_domain_must_be_verified_and_tenant_scoped(self):
        domain_a = create_domain_for_tenant(tenant=self.tenant_a, domain='example.com')
        domain_b = create_domain_for_tenant(tenant=self.tenant_b, domain='example.org')
        with self.assertRaises(ValidationError):
            set_primary_domain(tenant=self.tenant_a, domain_id=domain_a.id)
        domain_a.is_verified = True
        domain_a.status = TenantDomain.Status.ACTIVE
        domain_a.save()
        set_primary_domain(tenant=self.tenant_a, domain_id=domain_a.id)
        domain_a.refresh_from_db()
        self.assertTrue(domain_a.is_primary)
        with self.assertRaises(PermissionDenied):
            set_primary_domain(tenant=self.tenant_a, domain_id=domain_b.id)

    def test_ssl_provisioning_only_updates_state(self):
        domain = create_domain_for_tenant(tenant=self.tenant_a, domain='example.com')
        enqueue_ssl_provisioning(domain)
        domain.refresh_from_db()
        self.assertEqual(domain.ssl_status, TenantDomain.SSLStatus.PROVISIONING)
        self.assertIsNotNone(domain.ssl_last_checked_at)

    def test_domain_dashboard_blocks_request_without_active_tenant(self):
        domain = create_domain_for_tenant(tenant=self.tenant_b, domain='example.org')
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('domains:domain_detail', args=[domain.id]))
        self.assertEqual(response.status_code, 403)
