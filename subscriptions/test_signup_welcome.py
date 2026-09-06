from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from .models import Plan, PlanPrice, CustomerAcquisition
from .services import reserve_customer_acquisition


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   SITE_BASE_URL='https://pressnexa.example.com')
class SignupWelcomeTests(TestCase):
    def setUp(self):
        plan = Plan.objects.create(name='News Starter', code='news_starter')
        self.price = PlanPrice.objects.create(plan=plan, billing_cycle='monthly', amount=79800)

    def signup(self, email='reader@example.com'):
        return reserve_customer_acquisition(
            business_name='My News', publication_name='My News <script>bad</script>',
            publication_slug='my-news', email=email, mobile='9876543210',
            password='PrivatePass123!', plan_price=self.price, billing_months=1)

    def test_email_after_commit_contains_details_and_no_password(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            acquisition, checkout = self.signup()
            self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['reader@example.com'])
        for text in [acquisition.user.username, '9876543210', 'News Starter', '399', 'Payment pending', str(acquisition.uuid)]:
            self.assertIn(text, message.body)
        self.assertNotIn('PrivatePass123!', message.body)
        self.assertNotIn(acquisition.user.password, message.body)
        self.assertIn('https://pressnexa.example.com/account/login/', message.body)
        html = message.alternatives[0].content
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>bad</script>', html)
        self.assertNotIn('PrivatePass123!', html)

    def test_missing_optional_email_skips_mail(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.signup(email='')
        self.assertEqual(len(mail.outbox), 0)

    def test_transaction_rollback_does_not_send(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            try:
                with transaction.atomic():
                    self.signup()
                    raise ValueError('abort signup')
            except ValueError:
                pass
        self.assertEqual(callbacks, [])
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(CustomerAcquisition.objects.exists())

    def test_mail_failure_keeps_signup_successful(self):
        with patch('subscriptions.welcome.EmailMultiAlternatives.send', side_effect=OSError('SMTP offline')):
            with self.assertLogs('subscriptions.welcome', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    acquisition, _ = self.signup()
        self.assertTrue(CustomerAcquisition.objects.filter(pk=acquisition.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=acquisition.user_id).exists())
