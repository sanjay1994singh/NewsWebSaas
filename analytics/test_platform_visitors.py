from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import OperationalError
from django.http import HttpResponse, HttpResponseRedirect
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from .models import PlatformEnquiry, PlatformVisit, PlatformVisitor
from .tracking import COOKIE, SESSION_COOKIE, PlatformVisitorMiddleware


@override_settings(SECURE_SSL_REDIRECT=False, PLATFORM_VISITOR_TRACKING_ENABLED=True, STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class PlatformVisitorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='reader', email='reader@example.com', password='test-pass-234')
        self.admin = get_user_model().objects.create_user(username='platform', platform_role='super_admin')

    def test_public_visits_and_session_returning(self):
        first = self.client.get('/contact-us/?email=private@example.com', HTTP_USER_AGENT='Mozilla Chrome/123 Mobile', HTTP_REFERER='https://google.com/search?q=private')
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.cookies[COOKIE]['httponly'])
        self.assertEqual(first.cookies[COOKIE]['samesite'], 'Lax')
        self.assertIn('no-store', first['Cache-Control'])
        visit = PlatformVisit.objects.get()
        self.assertEqual(visit.path, '/contact-us/')
        self.assertEqual(visit.referrer_domain, 'google.com')
        self.assertEqual(visit.browser, 'Chrome')
        self.assertEqual(visit.device_type, 'mobile')
        self.client.get('/contact-us/')
        self.assertEqual(PlatformVisitor.objects.count(), 1)
        self.assertEqual(PlatformVisit.objects.values('session_id').distinct().count(), 1)
        self.assertFalse(PlatformVisit.objects.filter(is_returning=True).exists())
        del self.client.cookies[SESSION_COOKIE]
        self.client.get('/contact-us/')
        self.assertTrue(PlatformVisit.objects.first().is_returning)
        self.assertEqual(PlatformVisit.objects.values('session_id').distinct().count(), 2)
        Client().get('/contact-us/')
        self.assertEqual(PlatformVisitor.objects.count(), 2)

    def test_signed_cookie_tampering_starts_new_identity(self):
        self.client.get('/contact-us/')
        old = PlatformVisitor.objects.get().pk
        self.client.cookies[COOKIE] = str(old)
        self.client.get('/contact-us/')
        self.assertEqual(PlatformVisitor.objects.count(), 2)

    def test_opt_out_bots_and_non_public_routes(self):
        for headers in ({'HTTP_DNT': '1'}, {'HTTP_SEC_GPC': '1'}, {'HTTP_USER_AGENT': 'Googlebot'}):
            response = self.client.get('/contact-us/', **headers)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(COOKIE, response.cookies)
        self.client.get('/does-not-exist-at-all/')
        self.client.get('/saas-admin/visitors/')
        self.client.head('/contact-us/')
        self.assertEqual(PlatformVisit.objects.count(), 0)
        with override_settings(PLATFORM_VISITOR_TRACKING_ENABLED=False):
            self.client.get('/contact-us/')
        self.assertEqual(PlatformVisitor.objects.count(), 0)

    def test_malformed_referrer_does_not_break_page(self):
        self.assertEqual(self.client.get('/contact-us/', HTTP_REFERER='http://[').status_code, 200)
        self.assertEqual(PlatformVisit.objects.get().referrer_domain, '')

    def test_tracking_database_failure_does_not_break_page(self):
        with patch('analytics.tracking.visitor_for_request', side_effect=OperationalError('unavailable')):
            with self.assertLogs('analytics.tracking', level='ERROR'):
                response = self.client.get('/contact-us/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PlatformVisit.objects.count(), 0)

    def test_successful_login_links_browser_without_copying_credentials(self):
        self.client.get('/contact-us/')
        response = self.client.post(reverse('accounts:login'), {'username': 'reader', 'password': 'test-pass-234'})
        self.assertEqual(response.status_code, 302)
        event = PlatformVisit.objects.get(kind='login')
        self.assertEqual(event.user, self.user)
        self.assertEqual(PlatformVisitor.objects.count(), 1)
        self.assertIsNone(PlatformVisit.objects.get(kind='page').user)

    def test_successful_signup_redirect_records_account_event(self):
        from django.contrib.auth.models import AnonymousUser
        request = RequestFactory().post('/saas/signup/')
        request.user = AnonymousUser()
        request.tenant = None
        request.resolver_match = resolve('/saas/signup/')
        def signup_response(req):
            req.user = self.user
            return HttpResponseRedirect('/billing/saas/checkout/example/')
        response = PlatformVisitorMiddleware(signup_response)(request)
        self.assertEqual(PlatformVisit.objects.get(kind='signup').user, self.user)
        self.assertIn(COOKIE, response.cookies)

    def test_tenant_domain_never_creates_platform_tracking(self):
        from django.contrib.auth.models import AnonymousUser
        request = RequestFactory().get('/contact-us/')
        request.user = AnonymousUser()
        request.tenant = object()
        request.resolver_match = resolve('/contact-us/')
        PlatformVisitorMiddleware(lambda req: HttpResponse('tenant'))(request)
        self.assertEqual(PlatformVisitor.objects.count(), 0)

    def enquiry_data(self):
        return {'name': 'Ravi', 'email': 'ravi@example.com', 'phone': '+91 9876543210', 'message': 'I want a news website.', 'consent': 'on'}

    def test_enquiry_saved_and_linked_and_post_redirect_get(self):
        self.client.get('/contact-us/')
        response = self.client.post('/contact-us/', self.enquiry_data(), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your enquiry has been saved')
        enquiry = PlatformEnquiry.objects.get()
        self.assertEqual(enquiry.visitor, PlatformVisitor.objects.get())
        self.assertEqual(enquiry.phone, '+91 9876543210')
        self.assertIsNotNone(enquiry.consent_at)
        self.client.get('/contact-us/')
        self.assertEqual(PlatformEnquiry.objects.count(), 1)

    def test_enquiry_works_without_tracking(self):
        self.assertEqual(self.client.post('/contact-us/', self.enquiry_data(), HTTP_DNT='1').status_code, 302)
        self.assertIsNone(PlatformEnquiry.objects.get().visitor_id)
        self.assertEqual(PlatformVisitor.objects.count(), 0)

    def test_enquiry_validation_csrf_and_throttle(self):
        data = self.enquiry_data()
        data.pop('consent')
        self.assertEqual(self.client.post('/contact-us/', data).status_code, 400)
        data = self.enquiry_data()
        data['website'] = 'spam'
        self.assertEqual(self.client.post('/contact-us/', data).status_code, 400)
        self.assertEqual(Client(enforce_csrf_checks=True).post('/contact-us/', self.enquiry_data()).status_code, 403)
        self.assertEqual(PlatformEnquiry.objects.count(), 0)
        for _ in range(3):
            self.client.post('/contact-us/', {})
        self.assertEqual(self.client.post('/contact-us/', self.enquiry_data()).status_code, 429)
        self.assertEqual(PlatformEnquiry.objects.count(), 0)

    def test_admin_report_permissions_filters_and_enquiry_updates(self):
        self.client.get('/contact-us/')
        self.client.post('/contact-us/', self.enquiry_data())
        enquiry = PlatformEnquiry.objects.get()
        url = reverse('analytics:visitor_report')
        update = reverse('analytics:update_enquiry', args=[enquiry.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(update, {'status': 'closed'}).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ravi@example.com')
        self.assertEqual(response.context['metrics']['page_views'], 1)
        self.assertEqual(response.context['metrics']['visitors'], 1)
        self.assertContains(response, 'Daily visitors and views')
        self.assertContains(self.client.get(url, {'visitor': uuid4()}), 'No enquiries in this date range.')
        self.assertContains(self.client.get(url, {'start': 'invalid'}), 'Enter a valid date')
        self.assertEqual(self.client.post(update, {'status': 'invalid'}).status_code, 400)
        self.assertEqual(self.client.post(update, {'status': 'contacted', 'notes': 'Call tomorrow'}).status_code, 302)
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.status, 'contacted')
        self.assertEqual(enquiry.notes, 'Call tomorrow')
        # Viewing the dashboard must not inflate public traffic.
        self.assertEqual(PlatformVisit.objects.count(), 1)
