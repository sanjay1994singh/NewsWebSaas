from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve
from django.utils.html import escapejs

from .context_processors import google_analytics


@override_settings(
    SITE_BASE_URL='https://pressnexa.example.com',
    ALLOWED_HOSTS=['pressnexa.example.com', 'localhost', 'tenant.example.com'],
    GOOGLE_ANALYTICS_MEASUREMENT_ID='G-7839WK8E1T',
    GOOGLE_ANALYTICS_ENABLED=True,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class GoogleTagTests(SimpleTestCase):
    def request(self, path='/contact-us/', host='pressnexa.example.com', **headers):
        request = RequestFactory().get(path, HTTP_HOST=host, **headers)
        request.resolver_match = resolve(request.path)
        request.tenant = None
        request.user = AnonymousUser()
        return request

    def test_public_routes_receive_the_supplied_tag(self):
        for path in ['/', '/saas/', '/saas/signup/', '/contact-us/', '/about-us/', '/account/login/', '/privacy-policy/']:
            with self.subTest(path=path):
                self.assertEqual(google_analytics(self.request(path)), {'google_analytics_id': 'G-7839WK8E1T'})

    def test_private_routes_and_other_hosts_are_excluded(self):
        for path in ['/saas-admin/visitors/', '/admin/', '/account/profile/', '/billing/account/billing/', '/dashboard/']:
            self.assertEqual(google_analytics(self.request(path)), {})
        self.assertEqual(google_analytics(self.request(host='localhost')), {})
        self.assertEqual(google_analytics(self.request(host='tenant.example.com')), {})
        request = self.request()
        request.tenant = object()
        self.assertEqual(google_analytics(request), {})

    def test_opt_out_disabled_invalid_ids_and_posts(self):
        for header in ['HTTP_DNT', 'HTTP_SEC_GPC']:
            self.assertEqual(google_analytics(self.request(**{header: '1'})), {})
        with override_settings(GOOGLE_ANALYTICS_ENABLED=False):
            self.assertEqual(google_analytics(self.request()), {})
        for value in ['', 'G-invalid', "G-1234567890</script>"]:
            with override_settings(GOOGLE_ANALYTICS_MEASUREMENT_ID=value):
                self.assertEqual(google_analytics(self.request()), {})
        request = self.request()
        request.method = 'POST'
        self.assertEqual(google_analytics(request), {})

    def test_tag_occurs_once_in_shared_head_and_does_not_embed_contact_data(self):
        request = self.request('/contact-us/?email=private@example.com')
        context = {'request': request, 'user': request.user, **google_analytics(request)}
        html = render_to_string('base.html', context)
        self.assertEqual(html.count('https://www.googletagmanager.com/gtag/js?id=' + escapejs('G-7839WK8E1T')), 1)
        self.assertLess(html.index('Google tag (gtag.js)'), html.index('</head>'))
        self.assertNotIn('private@example.com', html)
        self.assertIn('window.pressNexaGoogleTagLoaded', html)
        self.assertIn('allow_google_signals: false', html)
        self.assertIn('window.location.origin + window.location.pathname', html)
        html = render_to_string('base.html', {'request': request, 'user': request.user})
        self.assertNotIn('googletagmanager.com', html)

    def test_standalone_landing_page_includes_tag_once(self):
        request = self.request('/')
        html = render_to_string('subscriptions/landing.html', {
            'request': request, 'user': request.user, **google_analytics(request),
        })
        self.assertEqual(html.count('https://www.googletagmanager.com/gtag/js?id='), 1)
        self.assertLess(html.index('Google tag (gtag.js)'), html.index('</head>'))
