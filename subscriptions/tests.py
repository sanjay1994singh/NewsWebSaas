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
from domains.models import TenantDomain
from tenants.models import Tenant, TenantMembership
from themes.models import TenantBranding, ThemeActivation

from .entitlements import get_feature_limit, tenant_has_feature, tenant_feature_limit
from .forms import CustomerSignupForm
from .models import (
    AddOn,
    BillingRecord,
    CustomerAcquisition,
    Feature,
    OnboardingAutomationPolicy,
    OnboardingReviewEvent,
    Plan,
    PlanChangeRequest,
    PlanFeature,
    PlanPrice,
    PlatformPurchaseAgreement,
    PlatformSupportContact,
    TenantOnboarding,
    TenantAddOn,
    TenantFeatureOverride,
    TenantSubscription,
    WebhookEvent,
)
from .pricing import calculate_checkout_pricing
from .services import (
    auto_publish_paid_onboardings,
    apply_verified_plan_change_checkout,
    calculate_plan_change_quote,
    create_tenant_after_verified_subscription,
    ensure_paid_tenant_integrity,
    process_webhook,
    create_plan_change_checkout,
    record_successful_subscription_payment,
    subscription_period_for_cycle,
    verify_razorpay_signature,
)
from .whatsapp import normalize_whatsapp_number


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
        self.assertEqual(billing_record.amount, 99950)
        self.assertEqual(billing_record.list_amount, 199900)
        self.assertEqual(billing_record.discount_percent, 50)
        self.assertEqual(billing_record.discount_amount, 99950)
        subscription = tenant.subscription
        self.assertIsNotNone(subscription.current_period_end)
        self.assertIsNotNone(subscription.charge_at)
        self.assertGreater(subscription.current_period_end, subscription.current_period_start)
        platform_domain = tenant.domains.get(is_primary=True)
        self.assertEqual(platform_domain.domain, 'checkout-media.live-app.in')
        self.assertTrue(platform_domain.is_verified)
        self.assertEqual(platform_domain.ssl_status, platform_domain.SSLStatus.ACTIVE)
        onboarding = tenant.commercial_onboarding
        self.assertEqual(onboarding.status, TenantOnboarding.Status.PUBLISHED)
        self.assertIsNotNone(onboarding.submitted_at)
        self.assertIsNotNone(onboarding.reviewed_at)
        self.assertIsNotNone(onboarding.published_at)
        self.assertEqual(onboarding.site_title, 'Checkout Media')
        tenant.refresh_from_db()
        self.assertEqual(tenant.status, Tenant.Status.ACTIVE)
        self.assertEqual(tenant.onboarding_status, Tenant.OnboardingStatus.COMPLETE)
        self.assertTrue(
            onboarding.review_events.filter(
                action=OnboardingReviewEvent.Action.SUBMITTED,
                notes='Auto-submitted after verified subscription payment.',
            ).exists()
        )
        self.assertTrue(
            onboarding.review_events.filter(
                action=OnboardingReviewEvent.Action.APPROVED,
                notes='Auto-approved after verified subscription payment.',
            ).exists()
        )
        self.assertTrue(
            onboarding.review_events.filter(
                action=OnboardingReviewEvent.Action.PUBLISHED,
                notes='Auto-published after verified subscription payment.',
            ).exists()
        )

    def test_manual_onboarding_policy_submits_but_does_not_publish_after_payment(self):
        OnboardingAutomationPolicy.objects.create(
            name='Manual review',
            mode=OnboardingAutomationPolicy.Mode.MANUAL,
            is_active=True,
        )
        acquisition = CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            business_name='Manual Media',
            publication_name='Manual News',
            publication_slug='manual-news',
            email='manual@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            provider_order_id='order_manual',
        )

        tenant = create_tenant_after_verified_subscription(
            acquisition=acquisition,
            provider_order_id='order_manual',
            payment_reference='pay_manual',
        )

        onboarding = tenant.commercial_onboarding
        tenant.refresh_from_db()
        self.assertEqual(onboarding.status, TenantOnboarding.Status.SUBMITTED_FOR_REVIEW)
        self.assertIsNone(onboarding.published_at)
        self.assertNotEqual(tenant.onboarding_status, Tenant.OnboardingStatus.COMPLETE)

    def test_delayed_onboarding_policy_uses_admin_delay_for_auto_publish(self):
        OnboardingAutomationPolicy.objects.create(
            name='Delayed review',
            mode=OnboardingAutomationPolicy.Mode.DELAYED,
            delay_minutes=45,
            is_active=True,
        )
        start = timezone.now() - timezone.timedelta(minutes=30)
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=start,
            current_period_start=start,
            current_period_end=start + timezone.timedelta(days=30),
        )
        onboarding = TenantOnboarding.objects.create(
            tenant=self.tenant,
            status=TenantOnboarding.Status.SUBMITTED_FOR_REVIEW,
            submitted_at=start,
        )

        self.assertEqual(auto_publish_paid_onboardings(), [])

        self.tenant.subscription.start_at = timezone.now() - timezone.timedelta(minutes=50)
        self.tenant.subscription.save(update_fields=['start_at', 'updated_at'])
        published = auto_publish_paid_onboardings()
        self.assertEqual(published, [onboarding])

    def test_subscription_verify_rejects_mismatched_order_id(self):
        acquisition = CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=self.price,
            business_name='Checkout Media',
            publication_name='Checkout News',
            publication_slug='checkout-news-secure',
            email='checkout@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            provider_order_id='order_expected',
            billing_months=1,
            list_amount=199900,
            discount_percent=50,
            discount_amount=99950,
            payable_amount=99950,
        )
        signature = hmac.new(b'razor_secret', b'order_wrong|pay_wrong', sha256).hexdigest()

        with override_settings(RAZORPAY_KEY_SECRET='razor_secret'):
            self.client.login(username='owner', password='testpass123')
            response = self.client.post(
                reverse('subscriptions:verify_subscription', kwargs={'acquisition_id': acquisition.uuid}),
                {
                    'razorpay_order_id': 'order_wrong',
                    'razorpay_payment_id': 'pay_wrong',
                    'razorpay_signature': signature,
                },
            )

        acquisition.refresh_from_db()
        self.assertRedirects(
            response,
            reverse('subscriptions:checkout', kwargs={'acquisition_id': acquisition.uuid}),
            fetch_redirect_response=False,
        )
        self.assertEqual(acquisition.status, CustomerAcquisition.Status.PAYMENT_PENDING)
        self.assertFalse(BillingRecord.objects.filter(razorpay_payment_id='pay_wrong').exists())

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
                'accepted_purchase_terms': 'on',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['publication_slug'], 'aaj-tak')

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_signup_requires_purchase_agreement_acceptance_before_payment(self):
        response = self.client.post(
            reverse('public_saas_signup'),
            {
                'business_name': 'Agreement News',
                'publication_name': 'Agreement News',
                'email': 'agreement@example.com',
                'mobile': '9999999999',
                'password': 'testpass123',
                'confirm_password': 'testpass123',
                'price_id': self.price.id,
                'billing_months': '1',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please read and accept the plan purchase terms to continue.')
        self.assertFalse(CustomerAcquisition.objects.filter(publication_slug='agreement-news').exists())

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_signup_shows_admin_purchase_agreement_and_continues_when_accepted(self):
        PlatformPurchaseAgreement.objects.create(
            title='Read Before Purchase',
            content='Plan activation starts after verified payment. No direct tenant is created before payment.',
            checkbox_label='I accept Press Nexa purchase rules.',
            is_active=True,
        )

        get_response = self.client.get(reverse('public_saas_signup'), {'price': self.price.id, 'months': '1'})
        self.assertContains(get_response, 'Read Before Purchase')
        self.assertContains(get_response, 'Plan activation starts after verified payment.')
        self.assertContains(get_response, 'I accept Press Nexa purchase rules.')

        response = self.client.post(
            reverse('public_saas_signup'),
            {
                'business_name': 'Accepted News',
                'publication_name': 'Accepted News',
                'email': 'accepted@example.com',
                'mobile': '9999999999',
                'password': 'testpass123',
                'confirm_password': 'testpass123',
                'price_id': self.price.id,
                'billing_months': '1',
                'accepted_purchase_terms': 'on',
            },
        )

        acquisition = CustomerAcquisition.objects.get(publication_slug='accepted-news')
        self.assertRedirects(response, reverse('subscriptions:checkout', kwargs={'acquisition_id': acquisition.uuid}), fetch_redirect_response=False)

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

        _, two_year_end, two_year_charge = subscription_period_for_cycle(start, PlanPrice.BillingCycle.MONTHLY, 24)
        self.assertEqual(two_year_end.date(), timezone.datetime(2028, 9, 3).date())
        self.assertEqual(two_year_charge, two_year_end)

    def test_offer_pricing_calculates_duration_discount(self):
        one_month = calculate_checkout_pricing(self.price, 1)
        twelve_months = calculate_checkout_pricing(self.price, 12)
        twenty_four_months = calculate_checkout_pricing(self.price, 24)

        self.assertEqual(one_month.list_amount, 199900)
        self.assertEqual(one_month.discount_amount, 99950)
        self.assertEqual(one_month.payable_amount, 99950)
        self.assertEqual(twelve_months.list_amount, 2398800)
        self.assertEqual(twelve_months.payable_amount, 1199400)
        self.assertEqual(twenty_four_months.list_amount, 4797600)
        self.assertEqual(twenty_four_months.payable_amount, 2398800)

    def test_public_plan_quote_returns_backend_calculated_duration_price(self):
        response = self.client.get(
            reverse('subscriptions:public_plan_quote'),
            {'price_id': self.price.id, 'months': '12'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['billing_months'], 12)
        self.assertEqual(data['list_display'], 'INR 23,988')
        self.assertEqual(data['payable_display'], 'INR 11,994')
        self.assertIn(f'price={self.price.id}', data['signup_url'])
        self.assertIn('months=12', data['signup_url'])

    def test_whatsapp_number_normalization_handles_leading_zero(self):
        self.assertEqual(normalize_whatsapp_number('06397712918'), '916397712918')
        self.assertEqual(normalize_whatsapp_number('9106397712918'), '916397712918')
        self.assertEqual(normalize_whatsapp_number('8384802152'), '918384802152')

    def test_pending_checkout_duration_can_change_before_payment(self):
        User = get_user_model()
        buyer = User.objects.create_user(username='buyer', password='testpass123')
        acquisition = CustomerAcquisition.objects.create(
            user=buyer,
            plan_price=self.price,
            business_name='Duration Media',
            publication_name='Duration News',
            publication_slug='duration-news',
            email='duration@example.com',
            mobile='9999999999',
            status=CustomerAcquisition.Status.PAYMENT_PENDING,
            billing_months=12,
            list_amount=2398800,
            discount_percent=50,
            discount_amount=1199400,
            payable_amount=1199400,
            provider_order_id='order_old',
            provider_payload={'order': {'id': 'order_old'}},
        )
        self.client.login(username='buyer', password='testpass123')
        session = self.client.session
        session['pending_checkout'] = {'order_id': 'order_old', 'billing_months': 12}
        session.save()

        response = self.client.post(
            reverse('subscriptions:checkout', kwargs={'acquisition_id': acquisition.uuid}),
            {'billing_months': '1'},
        )

        self.assertRedirects(response, reverse('subscriptions:checkout', kwargs={'acquisition_id': acquisition.uuid}))
        acquisition.refresh_from_db()
        self.assertEqual(acquisition.billing_months, 1)
        self.assertEqual(acquisition.list_amount, 199900)
        self.assertEqual(acquisition.discount_amount, 99950)
        self.assertEqual(acquisition.payable_amount, 99950)
        self.assertEqual(acquisition.provider_order_id, '')
        self.assertNotIn('pending_checkout', self.client.session)

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

    @override_settings(SITE_BASE_URL='https://pressnexa.live-app.in')
    def test_static_whatsapp_profile_button_redirects_to_tenant_domain_profile(self):
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
        )
        from domains.models import TenantDomain

        TenantDomain.objects.create(
            tenant=self.tenant,
            domain='billing-news.live-app.in',
            domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN,
            is_primary=True,
            is_verified=True,
            ssl_status=TenantDomain.SSLStatus.ACTIVE,
            status=TenantDomain.Status.ACTIVE,
        )
        self.client.login(username='owner', password='testpass123')

        response = self.client.get('/profile/')

        self.assertRedirects(response, 'https://billing-news.live-app.in/account/profile/', fetch_redirect_response=False)

    def test_billing_dashboard_focuses_on_current_plan_and_invoices(self):
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
        )
        invoice = BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_invoice_visible',
            amount=39900,
            list_amount=79800,
            discount_percent=50,
            discount_amount=39900,
            billing_months=1,
            currency='INR',
            status='paid',
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:billing_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current Plan')
        self.assertContains(response, 'Invoices')
        self.assertContains(response, 'INR 399')
        self.assertContains(response, reverse('subscriptions:view_invoice', kwargs={'record_id': invoice.id}))
        self.assertNotContains(response, 'Change Plan')
        self.assertNotContains(response, 'Add-ons')
        self.assertNotContains(response, 'Effective Features')

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

    def test_invoice_pdf_uses_active_admin_support_contact(self):
        PlatformSupportContact.objects.create(
            name='Primary Support',
            support_email='shriinfowaveprivatelimited@gmail.com',
            whatsapp_number='918279408396',
            is_active=True,
        )
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
        )
        invoice = BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_support_123',
            amount=199900,
            currency='INR',
            status='paid',
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:view_invoice', kwargs={'record_id': invoice.id}))

        self.assertContains(response, 'shriinfowaveprivatelimited@gmail.com')
        self.assertContains(response, '918279408396')

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

    def test_successful_renewals_create_billing_history_and_extend_period(self):
        start = timezone.datetime(2026, 9, 4, 10, 0, tzinfo=timezone.get_current_timezone())
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=start,
            current_period_start=start,
            current_period_end=timezone.datetime(2026, 10, 4, 10, 0, tzinfo=timezone.get_current_timezone()),
        )

        first = record_successful_subscription_payment(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=self.price,
            billing_months=1,
            provider_order_id='order_renew_1',
            payment_reference='pay_renew_1',
            amount=39900,
            list_amount=79800,
            discount_percent=50,
            discount_amount=39900,
        )
        subscription.refresh_from_db()

        self.assertEqual(first.period_start, timezone.datetime(2026, 10, 4, 10, 0, tzinfo=timezone.get_current_timezone()))
        self.assertEqual(first.period_end, timezone.datetime(2026, 11, 4, 10, 0, tzinfo=timezone.get_current_timezone()))
        self.assertEqual(subscription.current_period_end, first.period_end)

        second = record_successful_subscription_payment(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=self.price,
            billing_months=12,
            provider_order_id='order_renew_2',
            payment_reference='pay_renew_2',
            amount=478800,
            list_amount=957600,
            discount_percent=50,
            discount_amount=478800,
        )
        subscription.refresh_from_db()

        self.assertEqual(BillingRecord.objects.filter(tenant=self.tenant, status='paid').count(), 2)
        self.assertEqual(second.period_start, first.period_end)
        self.assertEqual(second.period_end, timezone.datetime(2027, 11, 4, 10, 0, tzinfo=timezone.get_current_timezone()))
        self.assertEqual(subscription.current_period_end, second.period_end)

    def test_duplicate_payment_reference_does_not_duplicate_or_extend_history(self):
        start = timezone.datetime(2026, 9, 4, 10, 0, tzinfo=timezone.get_current_timezone())
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            status=TenantSubscription.Status.ACTIVE,
            start_at=start,
            current_period_start=start,
            current_period_end=timezone.datetime(2026, 10, 4, 10, 0, tzinfo=timezone.get_current_timezone()),
        )

        record_successful_subscription_payment(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=self.price,
            billing_months=1,
            provider_order_id='order_same',
            payment_reference='pay_same',
            amount=39900,
            list_amount=79800,
            discount_percent=50,
            discount_amount=39900,
        )
        subscription.refresh_from_db()
        period_end = subscription.current_period_end

        record_successful_subscription_payment(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=self.price,
            billing_months=1,
            provider_order_id='order_same',
            payment_reference='pay_same',
            amount=39900,
            list_amount=79800,
            discount_percent=50,
            discount_amount=39900,
        )
        subscription.refresh_from_db()

        self.assertEqual(BillingRecord.objects.filter(tenant=self.tenant, razorpay_payment_id='pay_same').count(), 1)
        self.assertEqual(subscription.current_period_end, period_end)

    def test_upgrade_quote_credits_unused_current_plan_days(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=399800)
        now = timezone.now()
        period_start = now - timezone.timedelta(days=15)
        period_end = now + timezone.timedelta(days=15)
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=period_start,
            current_period_start=period_start,
            current_period_end=period_end,
            charge_at=period_end,
        )
        BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_current',
            amount=99950,
            billing_months=1,
            list_amount=199900,
            discount_percent=50,
            discount_amount=99950,
            period_start=period_start,
            period_end=period_end,
            currency='INR',
            status='paid',
        )

        quote = calculate_plan_change_quote(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=new_price,
            billing_months=1,
            now=now,
        )

        self.assertEqual(quote['list_amount'], 399800)
        self.assertEqual(quote['discount_amount'], 199900)
        self.assertEqual(quote['credit_amount'], 49975)
        self.assertEqual(quote['credit_source_amount'], 99950)
        self.assertEqual(quote['payable_amount'], 149925)
        self.assertEqual(quote['period_start'], now)

    def test_upgrade_quote_uses_current_subscription_paid_amount_only(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=399800)
        other_plan = Plan.objects.create(name='Old Other Plan', code=Plan.Code.NEWS_VIDEO, entitlements={})
        now = timezone.now()
        period_start = now - timezone.timedelta(days=10)
        period_end = now + timezone.timedelta(days=20)
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=period_start,
            current_period_start=period_start,
            current_period_end=period_end,
            charge_at=period_end,
        )
        BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_current_real',
            amount=39900,
            billing_months=1,
            list_amount=79800,
            discount_percent=50,
            discount_amount=39900,
            period_start=period_start,
            period_end=period_end,
            currency='INR',
            status='paid',
            payload={'plan_id': self.plan.id},
        )
        BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_wrong_overlap',
            amount=999900,
            billing_months=1,
            list_amount=999900,
            period_start=period_start,
            period_end=period_end,
            currency='INR',
            status='paid',
            payload={'plan_id': other_plan.id},
        )

        quote = calculate_plan_change_quote(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=new_price,
            billing_months=1,
            now=now,
        )

        expected_credit = round(39900 * ((period_end - now).total_seconds()) / ((period_end - period_start).total_seconds()))
        self.assertEqual(quote['credit_source_amount'], 39900)
        self.assertEqual(quote['credit_amount'], expected_credit)

    def test_upgrade_quote_never_falls_back_to_plan_price_for_credit(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=159800)
        now = timezone.now()
        period_start = now - timezone.timedelta(days=1)
        period_end = now + timezone.timedelta(days=29)
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=period_start,
            current_period_start=period_start,
            current_period_end=period_end,
            charge_at=period_end,
        )

        quote = calculate_plan_change_quote(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=new_price,
            billing_months=1,
            now=now,
        )

        self.assertEqual(quote['credit_source_amount'], 0)
        self.assertEqual(quote['credit_amount'], 0)
        self.assertEqual(quote['payable_amount'], 79900)

    def test_upgrade_quote_credits_demo_paid_amount_not_plan_price(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=159800)
        now = timezone.now()
        period_start = now - timezone.timedelta(days=1)
        period_end = now + timezone.timedelta(days=29)
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=period_start,
            current_period_start=period_start,
            current_period_end=period_end,
            charge_at=period_end,
        )
        BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_demo_one',
            amount=100,
            billing_months=1,
            list_amount=200,
            discount_percent=50,
            discount_amount=100,
            period_start=period_start,
            period_end=period_end,
            currency='INR',
            status='paid',
            payload={'plan_id': self.plan.id},
        )

        quote = calculate_plan_change_quote(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=new_price,
            billing_months=1,
            now=now,
        )

        expected_credit = round(100 * ((period_end - now).total_seconds()) / ((period_end - period_start).total_seconds()))
        self.assertEqual(quote['credit_source_amount'], 100)
        self.assertEqual(quote['credit_amount'], expected_credit)
        self.assertLess(quote['credit_amount'], 100)

    def test_upgrade_quote_uses_latest_paid_invoice_when_invoice_period_is_missing(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=159800)
        now = timezone.now()
        period_start = now - timezone.timedelta(days=1)
        period_end = now + timezone.timedelta(days=29)
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=period_start,
            current_period_start=period_start,
            current_period_end=period_end,
            charge_at=period_end,
        )
        BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_missing_period',
            amount=100,
            billing_months=1,
            list_amount=200,
            discount_percent=50,
            discount_amount=100,
            currency='INR',
            status='paid',
        )

        quote = calculate_plan_change_quote(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=new_price,
            billing_months=1,
            now=now,
        )

        expected_credit = round(100 * ((period_end - now).total_seconds()) / ((period_end - period_start).total_seconds()))
        self.assertEqual(quote['credit_source_amount'], 100)
        self.assertEqual(quote['credit_amount'], expected_credit)

    @override_settings(ALLOWED_HOSTS=['testserver', 'billing-news.live-app.in'])
    def test_tenant_domain_base_header_does_not_show_press_nexa_logo(self):
        TenantDomain.objects.create(
            tenant=self.tenant,
            domain='billing-news.live-app.in',
            domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN,
            is_primary=True,
            is_verified=True,
            status=TenantDomain.Status.ACTIVE,
        )
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=timezone.now(),
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
        )
        TenantOnboarding.objects.create(tenant=self.tenant, status=TenantOnboarding.Status.PUBLISHED)

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('subscriptions:upgrade_plan'), HTTP_HOST='billing-news.live-app.in')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Billing Media')
        self.assertNotContains(response, 'press-nexa-mark.svg')

    def test_verified_plan_upgrade_updates_subscription_and_keeps_billing_history(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=399800)
        now = timezone.now()
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=now - timezone.timedelta(days=15),
            current_period_start=now - timezone.timedelta(days=15),
            current_period_end=now + timezone.timedelta(days=15),
            charge_at=now + timezone.timedelta(days=15),
        )
        BillingRecord.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            razorpay_payment_id='pay_old',
            amount=99950,
            billing_months=1,
            list_amount=199900,
            discount_percent=50,
            discount_amount=99950,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            currency='INR',
            status='paid',
        )
        quote = calculate_plan_change_quote(
            tenant=self.tenant,
            subscription=subscription,
            plan_price=new_price,
            billing_months=12,
            now=now,
        )
        plan_change = PlanChangeRequest.objects.create(
            tenant=self.tenant,
            from_plan=self.plan,
            to_plan=new_plan,
            requested_by=self.user,
            change_type=PlanChangeRequest.ChangeType.UPGRADE,
            status=PlanChangeRequest.Status.PENDING_PAYMENT,
            plan_price=new_price,
            billing_months=quote['billing_months'],
            list_amount=quote['list_amount'],
            discount_percent=quote['discount_percent'],
            discount_amount=quote['discount_amount'],
            credit_amount=quote['credit_amount'],
            payable_amount=quote['payable_amount'],
            currency=quote['currency'],
            period_start=quote['period_start'],
            period_end=quote['period_end'],
        )

        apply_verified_plan_change_checkout(
            plan_change=plan_change,
            provider_order_id='order_upgrade',
            payment_reference='pay_upgrade',
            provider_signature='sig_upgrade',
        )

        subscription.refresh_from_db()
        plan_change.refresh_from_db()
        invoice = BillingRecord.objects.get(razorpay_payment_id='pay_upgrade')
        self.assertEqual(subscription.plan, new_plan)
        self.assertEqual(subscription.billing_months, 12)
        self.assertEqual(subscription.current_period_start, quote['period_start'])
        self.assertEqual(subscription.current_period_end, quote['period_end'])
        self.assertEqual(plan_change.status, PlanChangeRequest.Status.APPLIED)
        self.assertEqual(invoice.amount, quote['payable_amount'])
        self.assertEqual(invoice.list_amount, quote['list_amount'])
        self.assertEqual(invoice.discount_amount, quote['discount_amount'] + quote['credit_amount'])
        self.assertEqual(BillingRecord.objects.filter(tenant=self.tenant, status='paid').count(), 2)

    def test_plan_upgrade_verify_rejects_mismatched_order_id(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=399800)
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=timezone.now(),
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
        )
        plan_change = PlanChangeRequest.objects.create(
            tenant=self.tenant,
            from_plan=self.plan,
            to_plan=new_plan,
            requested_by=self.user,
            change_type=PlanChangeRequest.ChangeType.UPGRADE,
            status=PlanChangeRequest.Status.PENDING_PAYMENT,
            plan_price=new_price,
            billing_months=1,
            list_amount=399800,
            discount_percent=50,
            discount_amount=199900,
            payable_amount=199900,
            currency='INR',
            provider_order_id='order_expected',
            period_start=timezone.now(),
            period_end=timezone.now() + timezone.timedelta(days=30),
        )
        signature = hmac.new(b'razor_secret', b'order_wrong|pay_wrong', sha256).hexdigest()

        with override_settings(RAZORPAY_KEY_SECRET='razor_secret'):
            self.client.login(username='owner', password='testpass123')
            response = self.client.post(
                reverse('subscriptions:verify_plan_upgrade', kwargs={'plan_change_id': plan_change.uuid}),
                {
                    'razorpay_order_id': 'order_wrong',
                    'razorpay_payment_id': 'pay_wrong',
                    'razorpay_signature': signature,
                },
            )

        plan_change.refresh_from_db()
        self.assertRedirects(response, reverse('subscriptions:upgrade_plan'), fetch_redirect_response=False)
        self.assertEqual(plan_change.status, PlanChangeRequest.Status.PENDING_PAYMENT)
        self.assertFalse(BillingRecord.objects.filter(razorpay_payment_id='pay_wrong').exists())

    def test_upgrade_plan_quote_returns_backend_calculated_selected_plan_price(self):
        new_plan = Plan.objects.create(name='News Pro', code=Plan.Code.NEWS_PRO, entitlements={'news_articles': 2000})
        new_price = PlanPrice.objects.create(plan=new_plan, billing_cycle=PlanPrice.BillingCycle.MONTHLY, amount=399800)
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            billing_cycle=PlanPrice.BillingCycle.MONTHLY,
            billing_months=1,
            status=TenantSubscription.Status.ACTIVE,
            start_at=timezone.now(),
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
        )

        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('subscriptions:upgrade_plan_quote'),
            {'plan_price_id': new_price.id, 'months': '12'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['price'], 'INR 23,988')
        self.assertIn('Old plan credit', data['help_text'])
        self.assertEqual(data['action_label'], 'Upgrade')

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
        self.assertEqual(Page.objects.filter(tenant=self.tenant, is_published=True).count(), 9)
        self.assertTrue(Page.objects.filter(tenant=self.tenant, slug='editorial-policy').exists())
        self.assertTrue(Page.objects.filter(tenant=self.tenant, slug='privacy-policy', content__icontains='Billing News').exists())
        footer_menu = Menu.objects.get(tenant=self.tenant, location=Menu.Location.FOOTER)
        self.assertEqual(footer_menu.items.filter(link_type='page', is_enabled=True).count(), 9)

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
