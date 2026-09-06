from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from subscriptions.models import Plan, PlanPrice, CustomerAcquisition, TenantSubscription
from tenants.models import Tenant

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SECURE_SSL_REDIRECT=False,
 STORAGES={'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
 'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ProfileEmailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='owner', password='secretPass123')
        self.plan = Plan.objects.create(name='News Starter', code='news_starter')
        price = PlanPrice.objects.create(plan=self.plan, billing_cycle='monthly', amount=79800)
        self.acquisition = CustomerAcquisition.objects.create(user=self.user, plan_price=price,
            business_name='Local News', publication_name='Local News', publication_slug='local',
            mobile='9876543210', email='', payable_amount=39900, status='payment_pending')
        self.client.force_login(self.user)

    def save(self, email='owner@example.com'):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post('/account/profile/', {'full_name':'Owner Name', 'email':email})

    def test_first_email_sends_details_and_repeat_save_does_not(self):
        self.assertEqual(self.save().status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['owner@example.com'])
        for value in ['Owner Name', 'News Starter', '9876543210', '399', 'Continue payment']:
            self.assertIn(value, message.body)
        self.assertNotIn('secretPass123', message.body)
        self.acquisition.refresh_from_db()
        self.assertEqual(self.acquisition.email, 'owner@example.com')
        self.save()
        self.assertEqual(len(mail.outbox), 1)

    def test_active_workspace_uses_current_subscription_not_pending_message(self):
        tenant = Tenant.objects.create(owner=self.user, business_name='Local News', publication_name='Local News', slug='local', email='', status='active')
        TenantSubscription.objects.create(tenant=tenant, plan=self.plan, billing_cycle='monthly', status='active')
        self.acquisition.tenant = tenant
        self.acquisition.status = 'tenant_created'
        self.acquisition.save()
        self.save()
        self.assertIn('Active', mail.outbox[0].body)
        self.assertNotIn('Continue payment', mail.outbox[0].body)
        tenant.refresh_from_db()
        self.assertEqual(tenant.email, 'owner@example.com')

    def test_invalid_email_does_not_send(self):
        self.save('invalid')
        self.assertEqual(len(mail.outbox), 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_mail_failure_does_not_undo_profile_update(self):
        with patch('subscriptions.welcome.EmailMultiAlternatives.send', side_effect=OSError('offline')):
            with self.assertLogs('subscriptions.welcome', level='ERROR'):
                self.assertEqual(self.save().status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'owner@example.com')
