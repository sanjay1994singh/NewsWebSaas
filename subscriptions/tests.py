import hmac
import json
from hashlib import sha256

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from news.models import AuthorProfile
from pages.models import HomepageLayout, Menu, Page
from tenants.models import Tenant, TenantMembership
from themes.models import TenantBranding, ThemeActivation

from .entitlements import get_feature_limit, tenant_has_feature, tenant_feature_limit
from .forms import CustomerSignupForm
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
from .services import (
    auto_publish_paid_onboardings,
    create_tenant_after_verified_subscription,
    ensure_paid_tenant_integrity,
    process_webhook,
    subscription_period_for_cycle,
    verify_razorpay_signature,
)


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
                    'payment': {
                        'entity': {
                            'id': 'pay_test_123',
                            'order_id': 'order_test_123',
                        }
                    },
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
        self.assertEqual(acquisition.provider_payment_id, 'pay_test_123')
        self.assertEqual(acquisition.tenant.subscription.razorpay_payment_reference, 'pay_test_123')
        billing_record = acquisition.tenant.billing_records.get(razorpay_payment_id='pay_test_123')
        self.assertEqual(billing_record.razorpay_order_id, 'order_test_123')
        self.assertIn('webhook_event', billing_record.payload['checkout'])

    def test_verified_checkout_stores_order_payment_and_signature_references(self):
        acquisition = CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            business_name='Checkout Media',
            publication_name='Checkout News',
            publication_slug='checkout-news',
            email='checkout@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            provider_order_id='order_checkout_123',
        )

        tenant = create_tenant_after_verified_subscription(
            acquisition=acquisition,
            provider_order_id='order_checkout_123',
            payment_reference='pay_checkout_123',
            provider_signature='sig_checkout_123',
            provider_payload={'source': 'checkout_verify'},
        )

        acquisition.refresh_from_db()
        billing_record = tenant.billing_records.get(razorpay_payment_id='pay_checkout_123')
        self.assertEqual(acquisition.provider_order_id, 'order_checkout_123')
        self.assertEqual(acquisition.provider_payment_id, 'pay_checkout_123')
        self.assertEqual(acquisition.provider_signature, 'sig_checkout_123')
        self.assertEqual(billing_record.razorpay_order_id, 'order_checkout_123')
        self.assertEqual(billing_record.razorpay_signature, 'sig_checkout_123')
        self.assertEqual(billing_record.payload['provider_payment_id'], 'pay_checkout_123')
        subscription = tenant.subscription
        self.assertIsNotNone(subscription.current_period_end)
        self.assertIsNotNone(subscription.charge_at)
        self.assertGreater(subscription.current_period_end, subscription.current_period_start)

    def test_signup_reserves_site_slug_from_channel_or_paper_name(self):
        form = CustomerSignupForm(
            data={
                'business_name': 'Aaj Tak',
                'publication_name': 'Geeta',
                'email': 'owner@example.com',
                'mobile': '9999999999',
                'password': 'testpass123',
                'confirm_password': 'testpass123',
                'price_id': self.price.id,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['publication_slug'], 'aaj-tak')

    def test_sync_tenant_site_slugs_command_uses_channel_or_paper_name(self):
        self.tenant.business_name = 'Aaj Tak'
        self.tenant.publication_name = 'Geeta'
        self.tenant.slug = 'geeta'
        self.tenant.save(update_fields=['business_name', 'publication_name', 'slug', 'updated_at'])
        CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            tenant=self.tenant,
            business_name='Aaj Tak',
            publication_name='Geeta',
            publication_slug='geeta',
            email='owner@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.TENANT_CREATED,
        )

        out = type('Stream', (), {'write': lambda self, value: setattr(self, 'value', value)})()
        call_command('sync_tenant_site_slugs', stdout=out)

        self.tenant.refresh_from_db()
        acquisition = CustomerAcquisition.objects.get(tenant=self.tenant)
        self.assertEqual(self.tenant.slug, 'aaj-tak')
        self.assertEqual(acquisition.publication_slug, 'aaj-tak')

    def test_subscription_period_calculation_respects_billing_cycle(self):
        start = timezone.datetime(2026, 9, 3, 9, 0, tzinfo=timezone.get_current_timezone())

        _, monthly_end, monthly_charge = subscription_period_for_cycle(start, PlanPrice.BillingCycle.MONTHLY)
        _, yearly_end, yearly_charge = subscription_period_for_cycle(start, PlanPrice.BillingCycle.YEARLY)

        self.assertEqual(monthly_end.date(), timezone.datetime(2026, 10, 3).date())
        self.assertEqual(monthly_charge, monthly_end)
        self.assertEqual(yearly_end.date(), timezone.datetime(2027, 9, 3).date())
        self.assertEqual(yearly_charge, yearly_end)

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
                'payload': {'payment': {'entity': {'id': 'pay_failed_123', 'order_id': 'order_test_failed'}}},
            }
        ).encode('utf-8')
        signature = hmac.new(b'secret', body, sha256).hexdigest()

        process_webhook(body=body, signature=signature)

        acquisition.refresh_from_db()
        self.assertEqual(acquisition.status, CustomerAcquisition.Status.FAILED)
        self.assertEqual(acquisition.provider_payment_id, 'pay_failed_123')
        self.assertIn('failed_webhook', acquisition.provider_payload)

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

    def test_paid_onboarding_auto_publishes_after_waiting_period(self):
        old_start = timezone.now() - timezone.timedelta(minutes=31)
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=old_start,
            current_period_start=old_start,
        )
        subscription.save(update_fields=['start_at', 'current_period_start', 'updated_at'])
        onboarding = TenantOnboarding.objects.create(
            tenant=self.tenant,
            status=TenantOnboarding.Status.ONBOARDING,
        )

        published = auto_publish_paid_onboardings(older_than_minutes=30)

        self.assertEqual(published, [onboarding])
        onboarding.refresh_from_db()
        self.tenant.refresh_from_db()
        self.assertEqual(onboarding.status, TenantOnboarding.Status.PUBLISHED)
        self.assertIsNotNone(onboarding.published_at)
        self.assertEqual(self.tenant.status, Tenant.Status.ACTIVE)
        self.assertEqual(self.tenant.onboarding_status, Tenant.OnboardingStatus.COMPLETE)

    def test_auto_publish_skips_recent_or_rejected_onboardings(self):
        recent_start = timezone.now() - timezone.timedelta(minutes=10)
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=recent_start,
            current_period_start=recent_start,
        )
        recent = TenantOnboarding.objects.create(
            tenant=self.tenant,
            status=TenantOnboarding.Status.ONBOARDING,
        )

        published = auto_publish_paid_onboardings(older_than_minutes=30)

        self.assertEqual(published, [])
        recent.refresh_from_db()
        self.assertEqual(recent.status, TenantOnboarding.Status.ONBOARDING)

    def test_auto_publish_management_command_runs(self):
        out = type('Stream', (), {'write': lambda self, value: setattr(self, 'value', value)})()
        call_command('auto_publish_paid_onboardings', minutes=30, stdout=out)

        self.assertIn('Auto-published 0 onboarding record(s).', out.value)

    def test_backfill_subscription_periods_command_fills_missing_dates(self):
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=timezone.datetime(2026, 9, 3, 9, 0, tzinfo=timezone.get_current_timezone()),
            current_period_start=timezone.datetime(2026, 9, 3, 9, 0, tzinfo=timezone.get_current_timezone()),
        )

        out = type('Stream', (), {'write': lambda self, value: setattr(self, 'value', value)})()
        call_command('backfill_subscription_periods', tenant_slug=self.tenant.slug, stdout=out)

        subscription.refresh_from_db()
        self.assertIn('Backfilled 1 subscription period(s).', out.value)
        self.assertEqual(subscription.current_period_end.date(), timezone.datetime(2026, 10, 3).date())
        self.assertEqual(subscription.charge_at, subscription.current_period_end)

    def test_paid_tenant_integrity_audit_can_fix_safe_defaults(self):
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=timezone.now(),
            current_period_start=timezone.now(),
        )
        BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_order_id='order_audit_123',
            razorpay_payment_id='pay_audit_123',
            amount=self.price.amount,
            currency=self.price.currency,
            status='paid',
        )

        open_issues = ensure_paid_tenant_integrity(tenant=self.tenant, fix=False)
        self.assertTrue(open_issues)
        self.assertFalse(Category.objects.filter(tenant=self.tenant, slug='general').exists())

        fixed_issues = ensure_paid_tenant_integrity(tenant=self.tenant, fix=True)

        self.assertTrue(fixed_issues)
        self.assertTrue(Category.objects.filter(tenant=self.tenant, slug='general').exists())
        self.assertTrue(AuthorProfile.objects.filter(tenant=self.tenant, slug='editor').exists())
        self.assertTrue(TenantBranding.objects.filter(tenant=self.tenant).exists())
        self.assertTrue(ThemeActivation.objects.filter(tenant=self.tenant).exists())
        self.assertTrue(HomepageLayout.objects.filter(tenant=self.tenant, status=HomepageLayout.Status.PUBLISHED).exists())
        self.assertEqual(Menu.objects.filter(tenant=self.tenant).count(), 2)
        self.assertEqual(Page.objects.filter(tenant=self.tenant, is_published=True).count(), 4)

    def test_paid_tenant_integrity_management_command_runs(self):
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=timezone.now(),
            current_period_start=timezone.now(),
        )

        out = type('Stream', (), {'write': lambda self, value: setattr(self, 'value', value)})()
        call_command('audit_paid_tenant_integrity', tenant_slug=self.tenant.slug, fix=True, stdout=out)

        self.assertIn('Audit completed', out.value)


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
