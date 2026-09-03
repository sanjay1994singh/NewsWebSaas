import hmac
import json
from hashlib import sha256

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from tenants.models import Tenant, TenantMembership

from .entitlements import get_feature_limit, tenant_has_feature, tenant_feature_limit
from .models import (
    AddOn,
    BillingRecord,
    CustomerAcquisition,
    Feature,
    Plan,
    PlanFeature,
    PlanPrice,
    TenantOnboarding,
    TenantAddOn,
    TenantFeatureOverride,
    TenantSubscription,
    WebhookEvent,
)
from .services import process_webhook, verify_razorpay_signature


class SubscriptionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='owner', password='testpass123')
        self.tenant = Tenant.objects.create(
            owner=self.user,
            business_name='Billing Media',
            publication_name='Billing News',
            slug='billing-news',
            email='billing@example.com',
            status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=TenantMembership.Role.OWNER,
            status=TenantMembership.Status.ACTIVE,
        )
        self.plan = Plan.objects.create(
            name='Professional',
            code=Plan.Code.PROFESSIONAL,
            entitlements={'custom_domain': True, 'staff': 10},
        )
        self.price = PlanPrice.objects.create(plan=self.plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=199900)

    def test_entitlement_helpers_are_centralized(self):
        TenantSubscription.objects.create(tenant=self.tenant, plan=self.plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY)
        self.assertTrue(tenant_has_feature(self.tenant, 'custom_domain'))
        self.assertEqual(get_feature_limit(self.tenant, 'staff'), 10)

    def test_signature_verification_rejects_invalid_signature(self):
        body = b'{"id":"evt_1","event":"order.paid"}'
        signature = hmac.new(b'secret', body, sha256).hexdigest()
        self.assertTrue(verify_razorpay_signature(body=body, signature=signature, secret='secret'))
        with self.assertRaises(ValidationError):
            verify_razorpay_signature(body=body, signature='bad', secret='secret')

    @override_settings(RAZORPAY_WEBHOOK_SECRET='secret', RAZORPAY_ENVIRONMENT='test')
    def test_webhook_processing_is_idempotent(self):
        body = json.dumps({'id': 'evt_once', 'event': 'order.paid'}).encode('utf-8')
        signature = hmac.new(b'secret', body, sha256).hexdigest()
        first = process_webhook(body=body, signature=signature)
        second = process_webhook(body=body, signature=signature)
        self.assertEqual(first.id, second.id)
        self.assertEqual(WebhookEvent.objects.count(), 1)

    @override_settings(RAZORPAY_WEBHOOK_SECRET='secret')
    def test_webhook_rejects_bad_signature_before_storage(self):
        body = b'{"id":"evt_bad","event":"payment.failed"}'
        with self.assertRaises(ValidationError):
            process_webhook(body=body, signature='bad')
        self.assertEqual(WebhookEvent.objects.count(), 0)

    @override_settings(RAZORPAY_WEBHOOK_SECRET='secret', RAZORPAY_ENVIRONMENT='test')
    def test_order_webhook_creates_reserved_tenant(self):
        acquisition = CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            business_name='Order Media',
            publication_name='Order News',
            publication_slug='order-news',
            email='order@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            provider_order_id='order_test_123',
        )
        body = json.dumps(
            {
                'id': 'evt_order_paid',
                'event': 'order.paid',
                'payload': {
                    'order': {
                        'entity': {
                            'id': 'order_test_123',
                            'notes': {'acquisition_uuid': str(acquisition.uuid)},
                        }
                    }
                },
            }
        ).encode('utf-8')
        signature = hmac.new(b'secret', body, sha256).hexdigest()

        process_webhook(body=body, signature=signature)

        acquisition.refresh_from_db()
        self.assertIsNotNone(acquisition.tenant_id)
        self.assertEqual(acquisition.tenant.subscription.razorpay_payment_reference, 'order_test_123')

    @override_settings(RAZORPAY_WEBHOOK_SECRET='secret', RAZORPAY_ENVIRONMENT='test')
    def test_failed_payment_webhook_marks_acquisition_failed(self):
        acquisition = CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            business_name='Failed Media',
            publication_name='Failed News',
            publication_slug='failed-news',
            email='failed@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            provider_order_id='order_test_failed',
        )
        body = json.dumps(
            {
                'id': 'evt_payment_failed',
                'event': 'payment.failed',
                'payload': {'payment': {'entity': {'order_id': 'order_test_failed'}}},
            }
        ).encode('utf-8')
        signature = hmac.new(b'secret', body, sha256).hexdigest()

        process_webhook(body=body, signature=signature)

        acquisition.refresh_from_db()
        self.assertEqual(acquisition.status, CustomerAcquisition.Status.FAILED)

    def test_checkout_redirects_when_workspace_is_already_active(self):
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
        )
        TenantOnboarding.objects.create(tenant=self.tenant, status=TenantOnboarding.Status.PUBLISHED)
        acquisition = CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            business_name='Second Media',
            publication_name='Second News',
            publication_slug='second-news',
            email='second@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            provider_order_id='order_stale',
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:checkout', kwargs={'acquisition_id': acquisition.uuid}))

        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)

    def test_billing_dashboard_renders_add_on_actions_with_uuid_urls(self):
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
        )
        feature = Feature.objects.create(code='video_uploads', name='Video Uploads', category='video')
        add_on = AddOn.objects.create(
            feature=feature,
            name='Extra Video Pack',
            monthly_price=99900,
            yearly_price=999000,
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:billing_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('subscriptions:activate_add_on', kwargs={'add_on_id': add_on.uuid}))

    def test_invoice_pdf_download_is_available_to_tenant_owner(self):
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
        )
        invoice = BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_test_123',
            amount=199900,
            currency='INR',
            status='paid',
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:download_invoice', kwargs={'record_id': invoice.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_invoice_pdf_view_opens_inline_for_tenant_owner(self):
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
        )
        invoice = BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_view_123',
            amount=199900,
            currency='INR',
            status='paid',
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:view_invoice', kwargs={'record_id': invoice.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('inline', response['Content-Disposition'])

    def test_billing_dashboard_backfills_invoice_for_existing_successful_payment(self):
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            razorpay_payment_reference='pay_existing_123',
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:billing_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(BillingRecord.objects.filter(razorpay_payment_id='pay_existing_123').exists())
        self.assertContains(response, 'Download PDF')


class DynamicEntitlementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner_a = User.objects.create_user(username='owner-a', password='testpass123')
        self.owner_b = User.objects.create_user(username='owner-b', password='testpass123')
        self.tenant_a = Tenant.objects.create(
            owner=self.owner_a,
            business_name='Tenant A Media',
            publication_name='Tenant A News',
            slug='tenant-a-news',
            email='a@example.com',
            status=Tenant.Status.ACTIVE,
        )
        self.tenant_b = Tenant.objects.create(
            owner=self.owner_b,
            business_name='Tenant B Media',
            publication_name='Tenant B News',
            slug='tenant-b-news',
            email='b@example.com',
            status=Tenant.Status.ACTIVE,
        )
        self.plan = Plan.objects.create(name='News Starter', code=Plan.Code.NEWS_STARTER)
        self.epaper = Feature.objects.create(
            code='epaper',
            name='ePaper',
            category='publishing',
            feature_type=Feature.FeatureType.BOOLEAN,
        )
        self.news_articles = Feature.objects.create(
            code='news_articles',
            name='News Articles',
            category='content',
            feature_type=Feature.FeatureType.LIMIT,
            default_unit='articles',
        )
        PlanFeature.objects.create(plan=self.plan, feature=self.epaper, is_enabled=False)
        PlanFeature.objects.create(plan=self.plan, feature=self.news_articles, is_enabled=True, limit_value=100)
        TenantSubscription.objects.create(tenant=self.tenant_a, plan=self.plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY)
        TenantSubscription.objects.create(tenant=self.tenant_b, plan=self.plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY)

    def test_tenant_override_changes_one_tenant_without_affecting_same_plan_tenant(self):
        TenantFeatureOverride.objects.create(
            tenant=self.tenant_a,
            feature=self.epaper,
            override_type=TenantFeatureOverride.OverrideType.GRANT,
            is_enabled=True,
            reason='Pilot ePaper launch',
        )

        self.assertTrue(tenant_has_feature(self.tenant_a, 'epaper'))
        self.assertFalse(tenant_has_feature(self.tenant_b, 'epaper'))

    def test_feature_removed_or_disabled_from_plan_is_inaccessible(self):
        plan_feature = PlanFeature.objects.get(plan=self.plan, feature=self.news_articles)
        plan_feature.is_enabled = False
        plan_feature.save(update_fields=['is_enabled', 'updated_at'])

        self.assertFalse(tenant_has_feature(self.tenant_a, 'news_articles'))
        self.assertIsNone(tenant_feature_limit(self.tenant_a, 'news_articles'))

    def test_disabled_feature_is_blocked_through_direct_api_request(self):
        url = reverse('subscriptions:feature_access_check', args=[self.tenant_b.slug, 'epaper'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)

    def test_active_add_on_enables_feature_above_plan_default(self):
        add_on = AddOn.objects.create(
            feature=self.epaper,
            code='epaper-addon',
            name='ePaper Add-on',
            is_active=True,
        )
        TenantAddOn.objects.create(tenant=self.tenant_b, add_on=add_on)

        self.assertTrue(tenant_has_feature(self.tenant_b, 'epaper'))
