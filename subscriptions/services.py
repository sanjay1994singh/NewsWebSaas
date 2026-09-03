import hmac
import json
import re
import secrets
import string
from datetime import datetime
from hashlib import sha256

import razorpay
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from categories.models import Category
from news.models import AuthorProfile
from pages.models import HomepageLayout, Menu, MenuItem, Page
from tenants.models import Tenant, TenantMembership
from themes.models import TenantBranding, ThemeActivation

from .entitlements import get_effective_entitlements
from .models import (
    CustomerAcquisition,
    BillingRecord,
    OnboardingReviewEvent,
    PlanChangeRequest,
    PlanPrice,
    TenantAddOn,
    TenantOnboarding,
    TenantSubscription,
    WebhookEvent,
)
from .whatsapp import notify_payment_failed


def _add_months(value, months):
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, days_in_month[month - 1])
    return value.replace(year=year, month=month, day=day)


def subscription_period_for_cycle(start_at, billing_cycle):
    months = 12 if billing_cycle == PlanPrice.BillingCycle.YEARLY else 1
    end_at = _add_months(start_at, months)
    return start_at, end_at, end_at


def _append_issue(issues, code, message, fixed=False):
    issues.append({'code': code, 'message': message, 'fixed': fixed})


def _safe_page_content(tenant, title):
    return f'<p>{tenant.publication_name} will update this {title.lower()} page from the dashboard.</p>'


@transaction.atomic
def ensure_paid_tenant_integrity(*, tenant, fix=False):
    issues = []
    tenant = Tenant.objects.select_for_update().select_related('owner').get(pk=tenant.pk)

    try:
        subscription = tenant.subscription
    except TenantSubscription.DoesNotExist:
        _append_issue(issues, 'missing_subscription', 'Tenant has no subscription record.')
        subscription = None

    if subscription:
        if subscription.status != TenantSubscription.Status.ACTIVE:
            _append_issue(issues, 'subscription_not_active', f'Subscription status is {subscription.status}.')
        period_start = subscription.current_period_start or subscription.start_at
        if subscription.status == TenantSubscription.Status.ACTIVE and period_start and (
            not subscription.current_period_end or not subscription.charge_at
        ):
            _, period_end, charge_at = subscription_period_for_cycle(period_start, subscription.billing_cycle)
            if fix:
                update_fields = []
                if not subscription.current_period_start:
                    subscription.current_period_start = period_start
                    update_fields.append('current_period_start')
                if not subscription.current_period_end:
                    subscription.current_period_end = period_end
                    update_fields.append('current_period_end')
                if not subscription.charge_at:
                    subscription.charge_at = charge_at
                    update_fields.append('charge_at')
                subscription.save(update_fields=update_fields + ['updated_at'])
            _append_issue(issues, 'missing_period_dates', 'Subscription period end or charge date was missing.', fix)

    membership = TenantMembership.objects.filter(
        tenant=tenant,
        user=tenant.owner,
        status=TenantMembership.Status.ACTIVE,
    ).first()
    if membership is None:
        if fix:
            TenantMembership.objects.update_or_create(
                tenant=tenant,
                user=tenant.owner,
                defaults={
                    'role': TenantMembership.Role.OWNER,
                    'status': TenantMembership.Status.ACTIVE,
                    'joined_at': timezone.now(),
                },
            )
        _append_issue(issues, 'missing_owner_membership', 'Tenant owner had no active membership.', fix)

    acquisition = CustomerAcquisition.objects.filter(tenant=tenant).order_by('-created_at').first()
    billing = BillingRecord.objects.filter(tenant=tenant, status='paid').order_by('-created_at').first()
    if not acquisition:
        _append_issue(issues, 'missing_acquisition', 'No customer acquisition is linked to this tenant.')
    if not billing:
        _append_issue(issues, 'missing_paid_billing_record', 'No paid billing record exists for this tenant.')
    if acquisition and billing and fix:
        acq_fields = []
        if billing.razorpay_payment_id and not acquisition.provider_payment_id:
            acquisition.provider_payment_id = billing.razorpay_payment_id
            acq_fields.append('provider_payment_id')
        if billing.razorpay_order_id and not acquisition.provider_order_id:
            acquisition.provider_order_id = billing.razorpay_order_id
            acq_fields.append('provider_order_id')
        if acq_fields:
            acquisition.save(update_fields=acq_fields + ['updated_at'])
            _append_issue(issues, 'backfilled_acquisition_payment_reference', 'Acquisition payment references were backfilled from billing.', True)
        bill_fields = []
        if acquisition.provider_order_id and not billing.razorpay_order_id:
            billing.razorpay_order_id = acquisition.provider_order_id
            bill_fields.append('razorpay_order_id')
        if acquisition.provider_signature and not billing.razorpay_signature:
            billing.razorpay_signature = acquisition.provider_signature
            bill_fields.append('razorpay_signature')
        if bill_fields:
            billing.save(update_fields=bill_fields + ['updated_at'])
            _append_issue(issues, 'backfilled_billing_payment_reference', 'Billing payment references were backfilled from acquisition.', True)

    if not TenantOnboarding.objects.filter(tenant=tenant).exists():
        if fix:
            TenantOnboarding.objects.create(tenant=tenant, status=TenantOnboarding.Status.ONBOARDING)
        _append_issue(issues, 'missing_onboarding', 'Commercial onboarding record was missing.', fix)

    if not Category.objects.filter(tenant=tenant, slug='general').exists():
        if fix:
            Category.objects.create(tenant=tenant, slug='general', name='General', show_in_menu=True, is_active=True)
        _append_issue(issues, 'missing_default_category', 'Default General category was missing.', fix)

    if not AuthorProfile.objects.filter(tenant=tenant, slug='editor').exists():
        if fix:
            AuthorProfile.objects.create(tenant=tenant, slug='editor', user=tenant.owner, display_name=tenant.publication_name)
        _append_issue(issues, 'missing_default_author', 'Default editor author was missing.', fix)

    if not TenantBranding.objects.filter(tenant=tenant).exists():
        if fix:
            TenantBranding.objects.create(
                tenant=tenant,
                publication_name=tenant.publication_name,
                tagline=f'{tenant.publication_name} news and updates',
                contact_details={'email': tenant.email, 'mobile': tenant.mobile},
                copyright_text=f'Copyright {timezone.now().year} {tenant.publication_name}',
            )
        _append_issue(issues, 'missing_branding', 'Tenant branding was missing.', fix)

    theme = ThemeActivation.objects.filter(tenant=tenant).first()
    if theme is None:
        if fix:
            theme = ThemeActivation.objects.create(tenant=tenant)
        _append_issue(issues, 'missing_theme_activation', 'Theme activation was missing.', fix)

    active_theme = theme.active_theme if theme else ThemeActivation.ThemeKey.CLASSIC
    if not HomepageLayout.objects.filter(tenant=tenant, status=HomepageLayout.Status.PUBLISHED).exists():
        if fix:
            HomepageLayout.objects.create(tenant=tenant, status=HomepageLayout.Status.PUBLISHED, name='Homepage', theme_key=active_theme)
        _append_issue(issues, 'missing_homepage_layout', 'Published homepage layout was missing.', fix)

    for location, name in ((Menu.Location.HEADER, 'Header Menu'), (Menu.Location.FOOTER, 'Footer Menu')):
        menu = Menu.objects.filter(tenant=tenant, location=location).first()
        if menu is None:
            if fix:
                menu = Menu.objects.create(tenant=tenant, location=location, name=name)
            _append_issue(issues, f'missing_{location}_menu', f'{name} was missing.', fix)
        if menu and not menu.items.exists() and fix:
            MenuItem.objects.create(tenant=tenant, menu=menu, label='Home', link_type=MenuItem.LinkType.HOME, order=1)
            _append_issue(issues, f'missing_{location}_menu_items', f'{name} had no items.', True)
        elif menu and not menu.items.exists():
            _append_issue(issues, f'missing_{location}_menu_items', f'{name} had no items.', False)

    required_pages = [
        (Page.PageType.ABOUT, 'About Us', 'about-us'),
        (Page.PageType.CONTACT, 'Contact Us', 'contact-us'),
        (Page.PageType.PRIVACY, 'Privacy Policy', 'privacy-policy'),
        (Page.PageType.TERMS, 'Terms', 'terms'),
    ]
    for page_type, title, slug in required_pages:
        page = Page.objects.filter(tenant=tenant, slug=slug).first()
        if page is None:
            if fix:
                Page.objects.create(
                    tenant=tenant,
                    slug=slug,
                    title=title,
                    page_type=page_type,
                    content=_safe_page_content(tenant, title),
                    is_published=True,
                )
            _append_issue(issues, f'missing_{page_type}_page', f'{title} page was missing.', fix)
        elif fix and not page.is_published:
            page.is_published = True
            page.save(update_fields=['is_published', 'updated_at'])
            _append_issue(issues, f'unpublished_{page_type}_page', f'{title} page was unpublished.', True)
        elif not page.is_published:
            _append_issue(issues, f'unpublished_{page_type}_page', f'{title} page was unpublished.', False)

    get_effective_entitlements(tenant)
    return issues


def verify_razorpay_signature(*, body, signature, secret):
    expected = hmac.new(secret.encode('utf-8'), body, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ''):
        raise ValidationError("Invalid Razorpay signature.")
    return True


def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ValidationError("Razorpay keys are not configured.")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_razorpay_order_for_acquisition(acquisition):
    price = acquisition.plan_price
    client = get_razorpay_client()
    receipt = f"tenant_{acquisition.user_id}_{acquisition.uuid.hex[:24]}"
    order = client.order.create(
        {
            'amount': price.amount,
            'currency': price.currency,
            'receipt': receipt,
            'payment_capture': 1,
            'notes': {
                'acquisition_uuid': str(acquisition.uuid),
                'publication_slug': acquisition.publication_slug,
                'plan_price_id': str(price.id),
                'plan_code': price.plan.code,
                'billing_cycle': price.billing_cycle,
            },
        }
    )
    acquisition.provider_order_id = order['id']
    acquisition.provider_receipt = order.get('receipt', receipt)
    acquisition.provider_payload = {
        'order': order,
        'created_by': 'checkout',
    }
    acquisition.save(update_fields=['provider_order_id', 'provider_receipt', 'provider_payload', 'updated_at'])
    return {
        'key_id': settings.RAZORPAY_KEY_ID,
        'order_id': order['id'],
        'amount': order['amount'],
        'currency': order['currency'],
        'name': 'Press Nexa',
        'description': f"{price.plan.name} - {price.get_billing_cycle_display()}",
        'prefill': {
            'name': acquisition.publication_name,
            'email': acquisition.email,
            'contact': acquisition.mobile,
        },
    }


def verify_razorpay_checkout_signature(*, payment_id, order_id, signature):
    message = f"{order_id}|{payment_id}".encode('utf-8')
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode('utf-8'), message, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ''):
        raise ValidationError("Invalid Razorpay checkout signature.")
    return True


def _timestamp_from_razorpay(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OSError):
        return None


def _razorpay_entity(payload, entity_name):
    return payload.get('payload', {}).get(entity_name, {}).get('entity', {}) or {}


def _order_id_from_webhook(payload):
    payment = _razorpay_entity(payload, 'payment')
    order = _razorpay_entity(payload, 'order')
    return payment.get('order_id') or order.get('id') or ''


def _acquisition_uuid_from_webhook(payload):
    for entity_name in ('subscription', 'payment', 'order', 'invoice'):
        notes = _razorpay_entity(payload, entity_name).get('notes') or {}
        acquisition_uuid = notes.get('acquisition_uuid')
        if acquisition_uuid:
            return acquisition_uuid
    return ''


def _acquisition_for_order_webhook(payload, order_id):
    queryset = CustomerAcquisition.objects.select_related('plan_price__plan', 'user')
    if order_id:
        acquisition = queryset.filter(provider_order_id=order_id).order_by('-created_at').first()
        if acquisition:
            return acquisition
    acquisition_uuid = _acquisition_uuid_from_webhook(payload)
    if acquisition_uuid:
        return queryset.filter(uuid=acquisition_uuid).first()
    return None


def _payment_reference_from_webhook(payload):
    payment = _razorpay_entity(payload, 'payment')
    order = _razorpay_entity(payload, 'order')
    return payment.get('id') or payment.get('order_id') or order.get('id') or ''


def _sync_payment_from_webhook(*, payload, event_type):
    order_id = _order_id_from_webhook(payload)
    order_acquisition = _acquisition_for_order_webhook(payload, order_id)
    if order_acquisition:
        if event_type in ('payment.captured', 'order.paid') and order_id:
            create_tenant_after_verified_subscription(
                acquisition=order_acquisition,
                provider_order_id=order_id,
                payment_reference=_payment_reference_from_webhook(payload),
                provider_payload={'webhook_event': event_type, 'payload': payload},
            )
            return True
        if event_type == 'payment.failed':
            order_acquisition.status = CustomerAcquisition.Status.FAILED
            order_acquisition.provider_payment_id = _payment_reference_from_webhook(payload)
            order_acquisition.provider_payload = {
                **(order_acquisition.provider_payload or {}),
                'failed_webhook': {'event': event_type, 'payload': payload},
            }
            order_acquisition.save(update_fields=['status', 'provider_payment_id', 'provider_payload', 'updated_at'])
            if order_acquisition.tenant_id:
                TenantSubscription.objects.filter(tenant=order_acquisition.tenant).update(
                    status=TenantSubscription.Status.PAYMENT_ISSUE,
                    updated_at=timezone.now(),
                )
            notify_payment_failed(
                acquisition=order_acquisition,
                payment_reference=_payment_reference_from_webhook(payload) or order_id,
                checkout_url=f"{settings.SITE_BASE_URL}/billing/saas/checkout/{order_acquisition.uuid}/",
                profile_url=f"{settings.SITE_BASE_URL}/account/profile/",
            )
            return True
    return False

def _mobile_suffix(mobile):
    digits = re.sub(r'\D+', '', mobile or '')
    return digits[-4:] if digits else ''


def generate_customer_username(*, publication_name, mobile):
    User = get_user_model()
    base = slugify(publication_name).replace('-', '_')[:120] or 'pressnexa_user'
    suffix = _mobile_suffix(mobile)
    candidate = f'{base}_{suffix}' if suffix else base
    candidate = candidate[:150]
    if not User.objects.filter(username=candidate).exists():
        return candidate
    for index in range(2, 1000):
        reserve = f'_{index}'
        unique_candidate = f'{candidate[:150 - len(reserve)]}{reserve}'
        if not User.objects.filter(username=unique_candidate).exists():
            return unique_candidate
    return f'user_{secrets.token_hex(8)}'


def generate_temporary_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@transaction.atomic
def reserve_customer_acquisition(*, business_name, publication_name, publication_slug, email, mobile, password, plan_price):
    User = get_user_model()
    username = generate_customer_username(publication_name=publication_name, mobile=mobile)
    user = User.objects.create_user(username=username, email=email, password=password)
    acquisition = CustomerAcquisition.objects.create(
        user=user,
        plan_price=plan_price,
        business_name=business_name,
        publication_name=publication_name,
        publication_slug=publication_slug,
        email=email,
        mobile=mobile,
        status=CustomerAcquisition.Status.PAYMENT_PENDING,
    )
    checkout = {
        'acquisition_id': str(acquisition.id),
        'plan_id': plan_price.plan_id,
        'billing_cycle': plan_price.billing_cycle,
        'amount': plan_price.amount,
        'currency': plan_price.currency,
        'environment': settings.RAZORPAY_ENVIRONMENT,
    }
    return acquisition, checkout


@transaction.atomic
def reserve_customer_acquisition_for_user(*, user, business_name, publication_name, publication_slug, email, mobile, plan_price):
    acquisition = CustomerAcquisition.objects.create(
        user=user,
        plan_price=plan_price,
        business_name=business_name,
        publication_name=publication_name,
        publication_slug=publication_slug,
        email=email or user.email,
        mobile=mobile,
        status=CustomerAcquisition.Status.PAYMENT_PENDING,
    )
    checkout = {
        'acquisition_id': str(acquisition.id),
        'plan_id': plan_price.plan_id,
        'billing_cycle': plan_price.billing_cycle,
        'amount': plan_price.amount,
        'currency': plan_price.currency,
        'environment': settings.RAZORPAY_ENVIRONMENT,
    }
    return acquisition, checkout


@transaction.atomic
def update_pending_customer_acquisition(*, acquisition, business_name, publication_name, publication_slug, email, mobile, plan_price):
    acquisition = CustomerAcquisition.objects.select_for_update().get(pk=acquisition.pk)
    if acquisition.tenant_id or acquisition.status != CustomerAcquisition.Status.PAYMENT_PENDING:
        raise ValidationError("This workspace reservation can no longer be changed.")
    acquisition.plan_price = plan_price
    acquisition.business_name = business_name
    acquisition.publication_name = publication_name
    acquisition.publication_slug = publication_slug
    acquisition.email = email or acquisition.user.email
    acquisition.mobile = mobile
    acquisition.provider_order_id = ''
    acquisition.save(
        update_fields=[
            'plan_price',
            'business_name',
            'publication_name',
            'publication_slug',
            'email',
            'mobile',
            'provider_order_id',
            'updated_at',
        ]
    )
    checkout = {
        'acquisition_id': str(acquisition.id),
        'plan_id': plan_price.plan_id,
        'billing_cycle': plan_price.billing_cycle,
        'amount': plan_price.amount,
        'currency': plan_price.currency,
        'environment': settings.RAZORPAY_ENVIRONMENT,
    }
    return acquisition, checkout


@transaction.atomic
def create_tenant_after_verified_subscription(*, acquisition, provider_order_id, payment_reference='', provider_signature='', provider_payload=None):
    acquisition = CustomerAcquisition.objects.select_for_update().select_related('user', 'plan_price__plan').get(pk=acquisition.pk)
    if acquisition.tenant_id:
        update_fields = []
        if provider_order_id and acquisition.provider_order_id != provider_order_id:
            acquisition.provider_order_id = provider_order_id
            update_fields.append('provider_order_id')
        if payment_reference and acquisition.provider_payment_id != payment_reference:
            acquisition.provider_payment_id = payment_reference
            update_fields.append('provider_payment_id')
        if provider_signature and acquisition.provider_signature != provider_signature:
            acquisition.provider_signature = provider_signature
            update_fields.append('provider_signature')
        if provider_payload:
            acquisition.provider_payload = {
                **(acquisition.provider_payload or {}),
                'latest_verified_checkout': provider_payload,
            }
            update_fields.append('provider_payload')
        if update_fields:
            update_fields.append('updated_at')
            acquisition.save(update_fields=update_fields)
        return acquisition.tenant

    tenant, _ = Tenant.objects.get_or_create(
        slug=acquisition.publication_slug,
        defaults={
            'owner': acquisition.user,
            'business_name': acquisition.business_name,
            'publication_name': acquisition.publication_name,
            'status': Tenant.Status.TRIAL,
            'onboarding_status': Tenant.OnboardingStatus.IN_PROGRESS,
            'email': acquisition.email,
            'mobile': acquisition.mobile,
        },
    )
    TenantMembership.objects.get_or_create(
        tenant=tenant,
        user=acquisition.user,
        defaults={
            'role': TenantMembership.Role.OWNER,
            'status': TenantMembership.Status.ACTIVE,
            'joined_at': timezone.now(),
        },
    )
    period_start, period_end, charge_at = subscription_period_for_cycle(timezone.now(), acquisition.plan_price.billing_cycle)
    subscription, _ = TenantSubscription.objects.update_or_create(
        tenant=tenant,
        defaults={
            'plan': acquisition.plan_price.plan,
            'billing_cycle': acquisition.plan_price.billing_cycle,
            'razorpay_payment_reference': payment_reference or provider_order_id,
            'status': TenantSubscription.Status.ACTIVE,
            'start_at': period_start,
            'current_period_start': period_start,
            'current_period_end': period_end,
            'charge_at': charge_at,
        },
    )
    BillingRecord.objects.update_or_create(
        tenant=tenant,
        razorpay_payment_id=payment_reference or provider_order_id,
        defaults={
            'subscription': subscription,
            'razorpay_order_id': provider_order_id,
            'razorpay_invoice_id': '',
            'razorpay_signature': provider_signature,
            'amount': acquisition.plan_price.amount,
            'currency': acquisition.plan_price.currency,
            'status': 'paid',
            'payload': {
                'provider_order_id': provider_order_id,
                'provider_payment_id': payment_reference,
                'provider_signature_present': bool(provider_signature),
                'acquisition_uuid': str(acquisition.uuid),
                'plan': acquisition.plan_price.plan.name,
                'billing_cycle': acquisition.plan_price.billing_cycle,
                'checkout': provider_payload or {},
            },
        },
    )
    from .models import TenantOnboarding

    TenantOnboarding.objects.get_or_create(
        tenant=tenant,
        defaults={'status': TenantOnboarding.Status.ONBOARDING},
    )
    acquisition.tenant = tenant
    acquisition.provider_order_id = provider_order_id
    acquisition.provider_payment_id = payment_reference
    acquisition.provider_signature = provider_signature
    if provider_payload:
        acquisition.provider_payload = {
            **(acquisition.provider_payload or {}),
            'verified_checkout': provider_payload,
        }
    acquisition.status = CustomerAcquisition.Status.TENANT_CREATED
    acquisition.verified_at = timezone.now()
    acquisition.save(
        update_fields=[
            'tenant',
            'provider_order_id',
            'provider_payment_id',
            'provider_signature',
            'provider_payload',
            'status',
            'verified_at',
            'updated_at',
        ]
    )
    get_effective_entitlements(tenant)
    return tenant


@transaction.atomic
def submit_onboarding_for_review(*, onboarding, actor=None):
    onboarding.status = TenantOnboarding.Status.SUBMITTED_FOR_REVIEW
    onboarding.submitted_at = timezone.now()
    onboarding.save(update_fields=['status', 'submitted_at', 'updated_at'])
    OnboardingReviewEvent.objects.create(
        onboarding=onboarding,
        action=OnboardingReviewEvent.Action.SUBMITTED,
        actor=actor,
    )
    return onboarding


@transaction.atomic
def record_onboarding_review(*, onboarding, action, actor=None, notes=''):
    status_map = {
        OnboardingReviewEvent.Action.UNDER_REVIEW: TenantOnboarding.Status.UNDER_REVIEW,
        OnboardingReviewEvent.Action.CHANGES_REQUESTED: TenantOnboarding.Status.CHANGES_REQUESTED,
        OnboardingReviewEvent.Action.APPROVED: TenantOnboarding.Status.READY_TO_PUBLISH,
        OnboardingReviewEvent.Action.PUBLISHED: TenantOnboarding.Status.PUBLISHED,
        OnboardingReviewEvent.Action.REJECTED: TenantOnboarding.Status.REJECTED,
    }
    onboarding.status = status_map[action]
    onboarding.reviewer_notes = notes
    onboarding.reviewed_at = timezone.now()
    update_fields = ['status', 'reviewer_notes', 'reviewed_at', 'updated_at']
    if action == OnboardingReviewEvent.Action.PUBLISHED:
        onboarding.published_at = timezone.now()
        onboarding.tenant.status = Tenant.Status.ACTIVE
        onboarding.tenant.onboarding_status = Tenant.OnboardingStatus.COMPLETE
        onboarding.tenant.save(update_fields=['status', 'onboarding_status', 'updated_at'])
        update_fields.append('published_at')
    onboarding.save(update_fields=update_fields)
    OnboardingReviewEvent.objects.create(onboarding=onboarding, action=action, actor=actor, notes=notes)
    return onboarding


@transaction.atomic
def publish_onboarding(*, onboarding, actor=None, notes=''):
    onboarding = (
        TenantOnboarding.objects
        .select_for_update()
        .select_related('tenant')
        .get(pk=onboarding.pk)
    )
    if onboarding.status == TenantOnboarding.Status.PUBLISHED:
        return onboarding
    onboarding.status = TenantOnboarding.Status.PUBLISHED
    onboarding.reviewer_notes = notes
    onboarding.reviewed_at = timezone.now()
    onboarding.published_at = timezone.now()
    onboarding.tenant.status = Tenant.Status.ACTIVE
    onboarding.tenant.onboarding_status = Tenant.OnboardingStatus.COMPLETE
    onboarding.tenant.save(update_fields=['status', 'onboarding_status', 'updated_at'])
    onboarding.save(update_fields=['status', 'reviewer_notes', 'reviewed_at', 'published_at', 'updated_at'])
    OnboardingReviewEvent.objects.create(
        onboarding=onboarding,
        action=OnboardingReviewEvent.Action.PUBLISHED,
        actor=actor,
        notes=notes,
    )
    return onboarding


def auto_publish_paid_onboardings(*, older_than_minutes=30, limit=100):
    cutoff = timezone.now() - timezone.timedelta(minutes=older_than_minutes)
    eligible_statuses = [
        TenantOnboarding.Status.ONBOARDING,
        TenantOnboarding.Status.SUBMITTED_FOR_REVIEW,
        TenantOnboarding.Status.UNDER_REVIEW,
        TenantOnboarding.Status.APPROVED,
        TenantOnboarding.Status.READY_TO_PUBLISH,
    ]
    onboardings = (
        TenantOnboarding.objects
        .select_related('tenant', 'tenant__subscription')
        .filter(
            status__in=eligible_statuses,
            tenant__subscription__status=TenantSubscription.Status.ACTIVE,
            tenant__subscription__start_at__lte=cutoff,
            published_at__isnull=True,
        )
        .filter(Q(tenant__status=Tenant.Status.TRIAL) | Q(tenant__status=Tenant.Status.ACTIVE))
        .order_by('tenant__subscription__start_at', 'created_at')[:limit]
    )
    published = []
    for onboarding in onboardings:
        published.append(
            publish_onboarding(
                onboarding=onboarding,
                notes=f'Auto-published after {older_than_minutes} minutes without manual admin action.',
            )
        )
    return published


@transaction.atomic
def request_plan_change(*, tenant, to_plan, requested_by=None, effective_at=None, provider_reference=''):
    subscription = TenantSubscription.objects.select_for_update().select_related('plan').get(tenant=tenant)
    change_type = (
        PlanChangeRequest.ChangeType.UPGRADE
        if to_plan.version >= subscription.plan.version
        else PlanChangeRequest.ChangeType.DOWNGRADE
    )
    return PlanChangeRequest.objects.create(
        tenant=tenant,
        from_plan=subscription.plan,
        to_plan=to_plan,
        requested_by=requested_by,
        change_type=change_type,
        effective_at=effective_at,
        provider_reference=provider_reference,
    )


@transaction.atomic
def apply_verified_plan_change(*, plan_change, provider_reference=''):
    plan_change = PlanChangeRequest.objects.select_for_update().select_related('tenant', 'to_plan').get(pk=plan_change.pk)
    subscription = TenantSubscription.objects.select_for_update().get(tenant=plan_change.tenant)
    subscription.plan = plan_change.to_plan
    subscription.status = TenantSubscription.Status.ACTIVE
    subscription.save(update_fields=['plan', 'status', 'updated_at'])
    plan_change.status = PlanChangeRequest.Status.APPLIED
    plan_change.provider_reference = provider_reference or plan_change.provider_reference
    plan_change.save(update_fields=['status', 'provider_reference', 'updated_at'])
    get_effective_entitlements(plan_change.tenant)
    return subscription


@transaction.atomic
def activate_tenant_add_on(*, tenant_add_on, provider_payment_reference=''):
    tenant_add_on = TenantAddOn.objects.select_for_update().get(pk=tenant_add_on.pk)
    tenant_add_on.provider_payment_reference = provider_payment_reference or tenant_add_on.provider_payment_reference
    tenant_add_on.status = TenantAddOn.Status.ACTIVE
    tenant_add_on.is_active = True
    tenant_add_on.starts_at = tenant_add_on.starts_at or timezone.now()
    tenant_add_on.save(update_fields=['provider_payment_reference', 'status', 'is_active', 'starts_at', 'updated_at'])
    get_effective_entitlements(tenant_add_on.tenant)
    return tenant_add_on


@transaction.atomic
def process_webhook(*, body, signature, environment=None):
    environment = environment or settings.RAZORPAY_ENVIRONMENT
    verify_razorpay_signature(body=body, signature=signature, secret=settings.RAZORPAY_WEBHOOK_SECRET)
    payload = json.loads(body.decode('utf-8'))
    event_id = payload.get('id')
    event_type = payload.get('event')
    if not event_id or not event_type:
        raise ValidationError("Webhook payload missing id or event.")
    event, created = WebhookEvent.objects.get_or_create(
        environment=environment,
        provider='razorpay',
        event_id=event_id,
        defaults={'event_type': event_type, 'payload': payload},
    )
    if not created:
        return event
    _sync_payment_from_webhook(payload=payload, event_type=event_type)
    event.processed_at = timezone.now()
    event.save(update_fields=['processed_at', 'updated_at'])
    return event
