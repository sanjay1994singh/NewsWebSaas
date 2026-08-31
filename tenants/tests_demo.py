from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from categories.models import Category
from domains.models import TenantDomain
from news.models import NewsArticle
from pages.models import HomepageLayout, Menu
from tenants.models import Tenant
from themes.models import ThemeActivation


class DemoTenantCommandTests(TestCase):
    def test_demo_tenants_are_created_with_isolated_data(self):
        out = StringIO()
        call_command('create_demo_tenants', stdout=out)
        mathura = Tenant.objects.get(slug='mathura-news')
        bharat = Tenant.objects.get(slug='bharat-live')
        self.assertNotEqual(TenantDomain.objects.get(tenant=mathura).domain, TenantDomain.objects.get(tenant=bharat).domain)
        self.assertNotEqual(ThemeActivation.objects.get(tenant=mathura).active_theme, ThemeActivation.objects.get(tenant=bharat).active_theme)
        self.assertEqual(Category.objects.for_tenant(mathura).filter(name='Mathura').count(), 1)
        self.assertEqual(Category.objects.for_tenant(bharat).filter(name='National').count(), 1)
        self.assertEqual(NewsArticle.objects.for_tenant(mathura).filter(title__contains='National').count(), 0)
        self.assertEqual(Menu.objects.filter(tenant=mathura).count(), 1)
        self.assertEqual(HomepageLayout.objects.filter(tenant=bharat, status=HomepageLayout.Status.PUBLISHED).count(), 1)
