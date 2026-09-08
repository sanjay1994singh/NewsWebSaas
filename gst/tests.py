from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from gst.models import GSTSettings
from gst.services import tax_amount
from subscriptions.invoices import build_invoice_pdf
from subscriptions.models import PlanPrice
from subscriptions.pricing import calculate_checkout_pricing
from subscriptions.services import verify_captured_payment


class GSTTests(TestCase):
    def test_integer_paise_rounding(self):
        self.assertEqual(tax_amount(25, 18), 5)
        self.assertEqual(tax_amount(99950, 18), 17991)

    def test_admin_rate_controls_backend_quote(self):
        price = SimpleNamespace(amount=20000, billing_cycle=PlanPrice.BillingCycle.MONTHLY, currency='INR')
        quote = calculate_checkout_pricing(price)
        self.assertEqual((quote.taxable_amount, quote.tax_amount, quote.payable_amount), (10000, 1800, 11800))
        GSTSettings.objects.create(rate_percent=12)
        quote = calculate_checkout_pricing(price)
        self.assertEqual((quote.tax_rate_percent, quote.tax_amount, quote.payable_amount), (12, 1200, 11200))

    def test_zero_rate_is_preserved(self):
        GSTSettings.objects.create(rate_percent=0)
        price = SimpleNamespace(amount=20000, billing_cycle=PlanPrice.BillingCycle.MONTHLY, currency='INR')
        self.assertEqual(calculate_checkout_pricing(price).payable_amount, 10000)

    @patch('subscriptions.services.get_razorpay_client')
    def test_only_exact_captured_payment_is_accepted(self, client):
        payment = dict(id='pay_1', order_id='order_1', amount=11800, currency='INR', status='captured')
        client.return_value.payment.fetch.return_value = payment
        args = dict(payment_id='pay_1', order_id='order_1', amount=11800, currency='INR')
        self.assertEqual(verify_captured_payment(**args), payment)
        for field, value in [('amount', 10000), ('currency', 'USD'), ('status', 'authorized'), ('order_id', 'other'), ('id', 'other')]:
            client.return_value.payment.fetch.return_value = {**payment, field: value}
            with self.subTest(field=field), self.assertRaises(ValidationError):
                verify_captured_payment(**args)

    @patch('subscriptions.services.get_razorpay_client')
    def test_provider_error_fails_closed(self, client):
        client.return_value.payment.fetch.side_effect = RuntimeError('offline')
        with self.assertRaises(ValidationError):
            verify_captured_payment(payment_id='pay_1', order_id='order_1', amount=11800, currency='INR')

    def record(self, payload):
        return SimpleNamespace(id=1, created_at=timezone.now(), tenant=SimpleNamespace(
            publication_name='Test News', business_name='Test Business', email='test@example.com', mobile='123'),
            subscription=None, billing_months=1, list_amount=20000, discount_amount=10000,
            discount_percent=50, taxable_amount=10000, tax_rate_percent=18, tax_amount=1800,
            amount=11800, currency='INR', period_start=None, period_end=None,
            razorpay_payment_id='pay_test', razorpay_invoice_id='', status='paid', payload=payload)

    def test_legacy_invoice_has_no_gst_rows(self):
        pdf = build_invoice_pdf(self.record({}))
        self.assertNotIn(b'GSTIN:', pdf)
        self.assertNotIn(b'GST @', pdf)
        self.assertNotIn(b'Taxable value', pdf)

    def test_new_invoice_uses_frozen_gstin_after_admin_change(self):
        record = self.record({'gst': {'gstin': '09ABUCS7544P1Z2', 'supply_description': 'IT software product and services'}})
        GSTSettings.objects.create(gstin='07ABCDE1234F1Z5', rate_percent=12)
        pdf = build_invoice_pdf(record)
        self.assertIn(b'09ABUCS7544P1Z2', pdf)
        self.assertIn(b'GST @ 18%', pdf)
        self.assertNotIn(b'07ABCDE1234F1Z5', pdf)


class GSTCheckoutTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from subscriptions.models import Plan, CustomerAcquisition
        self.user = get_user_model().objects.create_user(username='gstowner')
        plan = Plan.objects.create(name='GST Plan', code='professional')
        self.price = PlanPrice.objects.create(plan=plan, billing_cycle='monthly', amount=20000)
        self.acquisition = CustomerAcquisition.objects.create(
            user=self.user, plan_price=self.price, business_name='GST News',
            publication_name='GST News', publication_slug='gst-news',
            email='gst@example.com', status='payment_pending')

    @patch('subscriptions.services.get_razorpay_client')
    def test_order_and_invoice_keep_original_tax_after_admin_edit(self, client):
        from subscriptions.services import create_razorpay_order_for_acquisition, create_tenant_after_verified_subscription
        client.return_value.order.create.return_value = dict(id='order_gst', amount=11800, currency='INR')
        create_razorpay_order_for_acquisition(self.acquisition)
        self.acquisition.refresh_from_db()
        self.assertEqual(self.acquisition.payable_amount, 11800)
        self.assertEqual(client.return_value.order.create.call_args.args[0]['amount'], 11800)
        GSTSettings.objects.create(rate_percent=12, gstin='07ABCDE1234F1Z5')
        tenant = create_tenant_after_verified_subscription(
            acquisition=self.acquisition, provider_order_id='order_gst', payment_reference='pay_gst')
        invoice = tenant.billing_records.get(razorpay_payment_id='pay_gst')
        self.assertEqual((invoice.amount, invoice.tax_amount, invoice.tax_rate_percent), (11800, 1800, 18))
        self.assertEqual(invoice.payload['gst']['gstin'], '09ABUCS7544P1Z2')

    def test_legacy_plan_change_endpoint_cannot_activate_from_posted_reference(self):
        from django.urls import reverse
        from tenants.models import Tenant, TenantMembership
        from subscriptions.models import Plan, TenantSubscription
        tenant = Tenant.objects.create(owner=self.user, business_name='GST', publication_name='GST', slug='gst-bypass')
        TenantMembership.objects.create(tenant=tenant, user=self.user, role='owner', status='active')
        subscription = TenantSubscription.objects.create(tenant=tenant, plan=self.price.plan, billing_cycle='monthly', status='active')
        target = Plan.objects.create(name='Upgrade', code='news_pro')
        self.client.force_login(self.user)
        response = self.client.post(reverse('subscriptions:change_plan'), {'plan_id': target.pk, 'provider_reference': 'fake_payment'})
        self.assertEqual(response.status_code, 302)
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, self.price.plan_id)

    @patch('subscriptions.services.get_razorpay_client')
    def test_upgrade_order_notes_and_invoice_snapshot(self, client):
        from tenants.models import Tenant
        from subscriptions.models import Plan, TenantSubscription
        from subscriptions.services import create_plan_change_checkout, apply_verified_plan_change_checkout
        tenant = Tenant.objects.create(owner=self.user, business_name='Upgrade GST', publication_name='Upgrade GST', slug='upgrade-gst')
        subscription = TenantSubscription.objects.create(tenant=tenant, plan=self.price.plan, billing_cycle='monthly', status='active')
        target = Plan.objects.create(name='GST Upgrade', code='news_pro')
        price = PlanPrice.objects.create(plan=target, billing_cycle='monthly', amount=40000)
        client.return_value.order.create.return_value = dict(id='order_upgrade_gst', amount=23600, currency='INR')
        change, checkout = create_plan_change_checkout(tenant=tenant, subscription=subscription, plan_price=price, billing_months=1, requested_by=self.user)
        notes = client.return_value.order.create.call_args.args[0]['notes']
        self.assertLessEqual(len(notes), 15)
        self.assertTrue(all(isinstance(value, str) for value in notes.values()))
        GSTSettings.objects.create(rate_percent=12, gstin='07ABCDE1234F1Z5')
        apply_verified_plan_change_checkout(plan_change=change, provider_order_id='order_upgrade_gst', payment_reference='pay_upgrade_gst')
        invoice = tenant.billing_records.get(razorpay_payment_id='pay_upgrade_gst')
        self.assertEqual(invoice.payload['gst']['gstin'], '09ABUCS7544P1Z2')
        self.assertEqual(invoice.tax_rate_percent, 18)
