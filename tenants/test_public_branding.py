from django.test import SimpleTestCase, override_settings
from django.template.loader import render_to_string
from tenants.models import Tenant


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PublicBrandingTests(SimpleTestCase):
    def test_public_pages_use_channel_not_publisher(self):
        tenant = Tenant(business_name='National 24', publication_name='Shravya')
        for template in ['epaper/reader.html', 'epaper/home.html', 'epaper/form.html', 'themes/shared/page.html', 'themes/theme_classic/homepage.html']:
            with self.subTest(template=template):
                from unittest.mock import patch
                with patch('epaper.templatetags.epaper_navigation.can_upload_epaper', return_value=False):
                    html = render_to_string(template, {'tenant': tenant, 'pages': [], 'public_site_slug': 'national24'})
                self.assertIn('National 24', html)
                self.assertNotIn('Shravya', html)

    def test_missing_channel_never_exposes_publisher(self):
        tenant = Tenant(business_name='  ', publication_name='Private publisher')
        self.assertEqual(tenant.public_name, 'News')


    def test_workspace_base_and_reporter_billing_branding(self):
        from types import SimpleNamespace
        from django.contrib.auth.models import AnonymousUser
        tenant = Tenant(business_name='National 24', publication_name='Shravya')
        request = SimpleNamespace(tenant=tenant, user=AnonymousUser(), path='/cms/')
        for name in ['news/article_dashboard.html', 'tenants/reporter_list.html', 'subscriptions/billing_dashboard.html']:
            with self.subTest(template=name):
                html = render_to_string(name, {'tenant':tenant, 'request':request, 'user':request.user, 'is_tenant_domain':True})
                self.assertEqual(html.count('class="channel-identity"'), 2)
                self.assertNotIn('Shravya', html)
                self.assertNotIn('class="tenant-brand-mark"', html)
                self.assertIn('National 24', html)
