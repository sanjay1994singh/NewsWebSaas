from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from domains.models import TenantDomain
from news.models import AuthorProfile, NewsArticle
from subscriptions.models import Plan, PlanPrice, TenantSubscription
from tenants.models import Tenant, TenantMembership

from .models import PageView
from .services import platform_metrics, tenant_analytics, tenant_cache_key


class AnalyticsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username='admin', platform_role=User.PlatformRole.SUPER_ADMIN)
        self.user_a = User.objects.create_user(username='a')
        self.user_b = User.objects.create_user(username='b')
        self.tenant_a = Tenant.objects.create(owner=self.user_a, business_name='A', publication_name='A', slug='a', email='a@example.com', status=Tenant.Status.ACTIVE)
        self.tenant_b = Tenant.objects.create(owner=self.user_b, business_name='B', publication_name='B', slug='b', email='b@example.com', status=Tenant.Status.TRIAL)
        TenantMembership.objects.create(tenant=self.tenant_a, user=self.user_a, role=TenantMembership.Role.OWNER, status=TenantMembership.Status.ACTIVE, joined_at=timezone.now())
        TenantDomain.objects.create(tenant=self.tenant_a, domain='a.example.com', domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN, is_verified=False)
        category = Category.objects.create(tenant=self.tenant_a, name='News', slug='news')
        author = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='Author', slug='author')
        article = NewsArticle.objects.create(tenant=self.tenant_a, category=category, author=author, title='Story', slug='story', content='Body', status=NewsArticle.Status.PUBLISHED)
        PageView.objects.create(tenant=self.tenant_a, path='/a', article=article, category=category, referrer_domain='google.com', device_type='mobile', occurred_at=timezone.now())
        PageView.objects.create(tenant=self.tenant_b, path='/b', referrer_domain='bing.com', device_type='desktop', occurred_at=timezone.now())

    def test_tenant_analytics_are_isolated(self):
        data = tenant_analytics(self.tenant_a)
        self.assertEqual(data['today_views'], 1)
        self.assertEqual(data['referrers'][0]['referrer_domain'], 'google.com')

    def test_platform_metrics_include_estimates(self):
        plan = Plan.objects.create(name='Starter', code=Plan.Code.STARTER)
        PlanPrice.objects.create(plan=plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=1000)
        TenantSubscription.objects.create(tenant=self.tenant_a, plan=plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, status=TenantSubscription.Status.ACTIVE)
        data = platform_metrics()
        self.assertEqual(data['total_tenants'], 2)
        self.assertEqual(data['paid_customers'], 1)
        self.assertGreaterEqual(data['domains_pending_verification'], 1)

    def test_cache_key_contains_tenant_identity(self):
        self.assertEqual(tenant_cache_key(self.tenant_a, 'homepage'), f'tenant:{self.tenant_a.id}:homepage')
