import hmac
import json
from hashlib import sha256

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from tenants.models import Tenant

from .entitlements import get_feature_limit, tenant_has_feature, tenant_feature_limit
from .models import (
    AddOn,
    CustomerAcquisition,
    Feature,
    Plan,
    PlanFeature,
    PlanPrice,
    RazorpayPlanMapping,
    TenantAddOn,
    TenantFeatureOverride,
    TenantSubscription,
    WebhookEvent,
)
from .services import create_subscription_checkout, process_webhook, verify_razorpay_signature


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
        self.plan = Plan.objects.create(
            name='Professional',
            code=Plan.Code.PROFESSIONAL,
            entitlements={'custom_domain': True, 'staff': 10},
        )
        self.price = PlanPrice.objects.create(plan=self.plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=199900)
        RazorpayPlanMapping.objects.create(price=self.price, environment=RazorpayPlanMapping.Environment.TEST, razorpay_plan_id='plan_test_123')

    def test_entitlement_helpers_are_centralized(self):
        TenantSubscription.objects.create(tenant=self.tenant, plan=self.plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY)
        self.assertTrue(tenant_has_feature(self.tenant, 'custom_domain'))
        self.assertEqual(get_feature_limit(self.tenant, 'staff'), 10)

    @override_settings(RAZORPAY_ENVIRONMENT='test')
    def test_checkout_uses_backend_price_and_environment_mapping(self):
        checkout = create_subscription_checkout(tenant=self.tenant, price_id=self.price.id, quantity=2)
        self.assertEqual(checkout['amount'], 199900)
        self.assertEqual(checkout['razorpay_plan_id'], 'plan_test_123')
        self.assertEqual(checkout['quantity'], 2)

    def test_signature_verification_rejects_invalid_signature(self):
        body = b'{"id":"evt_1","event":"subscription.activated"}'
        signature = hmac.new(b'secret', body, sha256).hexdigest()
        self.assertTrue(verify_razorpay_signature(body=body, signature=signature, secret='secret'))
        with self.assertRaises(ValidationError):
            verify_razorpay_signature(body=body, signature='bad', secret='secret')

    @override_settings(RAZORPAY_WEBHOOK_SECRET='secret', RAZORPAY_ENVIRONMENT='test')
    def test_webhook_processing_is_idempotent(self):
        body = json.dumps({'id': 'evt_once', 'event': 'subscription.activated'}).encode('utf-8')
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
    def test_subscription_webhook_creates_reserved_tenant(self):
        acquisition = CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            business_name='Webhook Media',
            publication_name='Webhook News',
            publication_slug='webhook-news',
            email='webhook@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            provider_subscription_id='sub_test_123',
        )
        body = json.dumps(
            {
                'id': 'evt_subscription_active',
                'event': 'subscription.activated',
                'payload': {
                    'subscription': {
                        'entity': {
                            'id': 'sub_test_123',
                            'status': 'active',
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
        self.assertEqual(acquisition.tenant.subscription.status, TenantSubscription.Status.ACTIVE)

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
            provider_subscription_id='order_test_123',
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
        self.assertEqual(acquisition.tenant.subscription.razorpay_subscription_id, 'order_test_123')

    @override_settings(RAZORPAY_WEBHOOK_SECRET='secret', RAZORPAY_ENVIRONMENT='test')
    def test_failed_payment_webhook_marks_existing_subscription_issue(self):
        tenant_subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            razorpay_subscription_id='sub_test_failed',
            status=TenantSubscription.Status.ACTIVE,
        )
        body = json.dumps(
            {
                'id': 'evt_payment_failed',
                'event': 'payment.failed',
                'payload': {'payment': {'entity': {'subscription_id': 'sub_test_failed'}}},
            }
        ).encode('utf-8')
        signature = hmac.new(b'secret', body, sha256).hexdigest()

        process_webhook(body=body, signature=signature)

        tenant_subscription.refresh_from_db()
        self.assertEqual(tenant_subscription.status, TenantSubscription.Status.PAYMENT_ISSUE)


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
