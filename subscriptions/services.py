import hmac
import json
import re
import secrets
import string
from datetime import datetime
from hashlib import sha256
from urllib.parse import urlparse

import razorpay
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from categories.models import Category
from domains.models import TenantDomain
from news.models import AuthorProfile
from pages.models import HomepageLayout, Menu, MenuItem, Page
from tenants.models import Tenant, TenantMembership
from themes.models import TenantBranding, ThemeActivation

from .entitlements import get_effective_entitlements
from .models import (
    CustomerAcquisition,
    BillingRecord,
    OnboardingAutomationPolicy,
    OnboardingReviewEvent,
    PlanChangeRequest,
    PlanPrice,
    PurchaseAgreementAcceptance,
    TenantAddOn,
    TenantOnboarding,
    TenantSubscription,
    WebhookEvent,
)
from .pricing import calculate_checkout_pricing, money_display, monthly_price_for_plan, normalize_billing_months
from .whatsapp import notify_payment_failed


def _add_months(value, months):
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, days_in_month[month - 1])
    return value.replace(year=year, month=month, day=day)


def subscription_period_for_cycle(start_at, billing_cycle, billing_months=None):
    months = normalize_billing_months(billing_months) if billing_months else 12 if billing_cycle == PlanPrice.BillingCycle.YEARLY else 1
    end_at = _add_months(start_at, months)
    return start_at, end_at, end_at


def next_subscription_period_start(subscription, now=None):
    now = now or timezone.now()
    if (
        subscription
        and subscription.status == TenantSubscription.Status.ACTIVE
        and subscription.current_period_end
        and subscription.current_period_end > now
    ):
        return subscription.current_period_end
    return now


def _paid_record_covering_current_period(tenant, now):
    return (
        BillingRecord.objects
        .filter(tenant=tenant, status='paid', period_start__lte=now, period_end__gt=now)
        .order_by('-period_end', '-created_at')
        .first()
    )


def _paid_record_for_subscription_period(tenant, subscription, now):
    period_queryset = (
        BillingRecord.objects
        .filter(
            tenant=tenant,
            subscription=subscription,
            status='paid',
            period_start__lte=now,
            period_end__gt=now,
        )
        .order_by('-period_end', '-created_at')
    )
    for record in period_queryset:
        if _billing_record_matches_subscription_plan(record, subscription):
            return record

    fallback_queryset = (
        BillingRecord.objects
        .filter(
            tenant=tenant,
            subscription=subscription,
            status='paid',
        )
        .order_by('-period_end', '-created_at')
    )
    for record in fallback_queryset:
        if _billing_record_matches_subscription_plan(record, subscription):
            return record
    return None


def _billing_record_matches_subscription_plan(record, subscription):
    try:
        payload = record.payload or {}
        checkout = payload.get('checkout') or {}
        plan_id = payload.get('plan_id') or checkout.get('plan_id')
        if plan_id:
            return int(plan_id) == subscription.plan_id
    except (TypeError, ValueError):
        return False
    return True


def active_onboarding_policy():
    policy = OnboardingAutomationPolicy.objects.filter(is_active=True).order_by('-updated_at', '-created_at').first()
    if policy:
        return policy
    return OnboardingAutomationPolicy(mode=OnboardingAutomationPolicy.Mode.INSTANT, delay_minutes=30)


def submit_onboarding_after_payment(*, onboarding, actor=None, now=None):
    now = now or timezone.now()
    onboarding.status = TenantOnboarding.Status.SUBMITTED_FOR_REVIEW
    onboarding.submitted_at = onboarding.submitted_at or now
    onboarding.save(update_fields=['status', 'submitted_at', 'updated_at'])
    OnboardingReviewEvent.objects.get_or_create(
        onboarding=onboarding,
        action=OnboardingReviewEvent.Action.SUBMITTED,
        defaults={
            'actor': actor,
            'notes': 'Auto-submitted after verified subscription payment.',
        },
    )
    return onboarding


def auto_approve_and_publish_onboarding(*, onboarding, actor=None, notes='Auto-approved and published after verified subscription payment.', now=None):
    now = now or timezone.now()
    onboarding.status = TenantOnboarding.Status.PUBLISHED
    onboarding.submitted_at = onboarding.submitted_at or now
    onboarding.reviewed_at = now
    onboarding.published_at = now
    onboarding.reviewer_notes = notes
    onboarding.tenant.status = Tenant.Status.ACTIVE
    onboarding.tenant.onboarding_status = Tenant.OnboardingStatus.COMPLETE
    onboarding.tenant.save(update_fields=['status', 'onboarding_status', 'updated_at'])
    onboarding.save(update_fields=['status', 'submitted_at', 'reviewed_at', 'published_at', 'reviewer_notes', 'updated_at'])
    OnboardingReviewEvent.objects.get_or_create(
        onboarding=onboarding,
        action=OnboardingReviewEvent.Action.APPROVED,
        defaults={
            'actor': actor,
            'notes': 'Auto-approved after verified subscription payment.',
        },
    )
    OnboardingReviewEvent.objects.get_or_create(
        onboarding=onboarding,
        action=OnboardingReviewEvent.Action.PUBLISHED,
        defaults={
            'actor': actor,
            'notes': 'Auto-published after verified subscription payment.',
        },
    )
    ensure_required_tenant_pages(tenant=onboarding.tenant)
    return onboarding


def calculate_plan_change_quote(*, tenant, subscription, plan_price, billing_months=1, now=None):
    now = now or timezone.now()
    checkout_pricing = calculate_checkout_pricing(plan_price, billing_months)
    period_start = now
    credit_amount = 0
    remaining_days = 0
    total_days = 0
    is_same_plan = subscription and subscription.plan_id == plan_price.plan_id
    if is_same_plan:
        period_start = next_subscription_period_start(subscription, now)
    elif (
        subscription
        and subscription.status == TenantSubscription.Status.ACTIVE
        and subscription.current_period_start
        and subscription.current_period_end
        and subscription.current_period_end > now
    ):
        paid_record = _paid_record_for_subscription_period(tenant, subscription, now)
        paid_amount = paid_record.amount if paid_record else 0
        total_seconds = max((subscription.current_period_end - subscription.current_period_start).total_seconds(), 1)
        remaining_seconds = max((subscription.current_period_end - now).total_seconds(), 0)
        credit_amount = min(round(paid_amount * remaining_seconds / total_seconds), checkout_pricing.payable_amount)
        total_days = max((subscription.current_period_end.date() - subscription.current_period_start.date()).days, 1)
        remaining_days = max((subscription.current_period_end.date() - now.date()).days, 0)
    period_start, period_end, _ = subscription_period_for_cycle(period_start, plan_price.billing_cycle, checkout_pricing.billing_months)
    payable_amount = max(checkout_pricing.payable_amount - credit_amount, 0)
    return {
        'billing_months': checkout_pricing.billing_months,
        'billing_label': checkout_pricing.billing_label,
        'list_amount': checkout_pricing.list_amount,
        'discount_percent': checkout_pricing.discount_percent,
        'discount_amount': checkout_pricing.discount_amount,
        'credit_amount': credit_amount,
        'payable_amount': payable_amount,
        'currency': checkout_pricing.currency,
        'period_start': period_start,
        'period_end': period_end,
        'remaining_days': remaining_days,
        'total_days': total_days,
        'credit_source_amount': paid_amount if not is_same_plan else 0,
        'list_display': money_display(checkout_pricing.list_amount, checkout_pricing.currency),
        'discount_display': money_display(checkout_pricing.discount_amount, checkout_pricing.currency),
        'credit_display': money_display(credit_amount, checkout_pricing.currency),
        'credit_source_display': money_display(paid_amount if not is_same_plan else 0, checkout_pricing.currency),
        'payable_display': money_display(payable_amount, checkout_pricing.currency),
    }


def record_successful_subscription_payment(
    *,
    tenant,
    subscription,
    plan_price,
    billing_months,
    provider_order_id='',
    payment_reference='',
    provider_signature='',
    amount=0,
    list_amount=0,
    discount_percent=0,
    discount_amount=0,
    period_start=None,
    provider_payload=None,
):
    payment_id = payment_reference or provider_order_id
    if not payment_id:
        raise ValidationError("A payment reference is required to record billing history.")
    period_start = period_start or next_subscription_period_start(subscription)
    period_start, period_end, charge_at = subscription_period_for_cycle(
        period_start,
        plan_price.billing_cycle,
        billing_months,
    )
    record, created = BillingRecord.objects.update_or_create(
        tenant=tenant,
        razorpay_payment_id=payment_id,
        defaults={
            'subscription': subscription,
            'razorpay_order_id': provider_order_id,
            'razorpay_invoice_id': '',
            'razorpay_signature': provider_signature,
            'amount': amount,
            'billing_months': billing_months,
            'list_amount': list_amount,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'period_start': period_start,
            'period_end': period_end,
            'currency': plan_price.currency,
            'status': 'paid',
            'payload': {
                'provider_order_id': provider_order_id,
                'provider_payment_id': payment_reference,
                'provider_signature_present': bool(provider_signature),
                'plan': plan_price.plan.name,
                'plan_id': plan_price.plan_id,
                'billing_cycle': plan_price.billing_cycle,
                'billing_months': billing_months,
                'list_amount': list_amount,
                'discount_percent': discount_percent,
                'discount_amount': discount_amount,
                'payable_amount': amount,
                'period_start': period_start.isoformat() if period_start else '',
                'period_end': period_end.isoformat() if period_end else '',
                'checkout': provider_payload or {},
            },
        },
    )
    if created:
        subscription.plan = plan_price.plan
        subscription.billing_cycle = plan_price.billing_cycle
        subscription.billing_months = billing_months
        subscription.razorpay_payment_reference = payment_id
        subscription.status = TenantSubscription.Status.ACTIVE
        if not subscription.start_at:
            subscription.start_at = period_start
        subscription.current_period_start = period_start
        subscription.current_period_end = period_end
        subscription.charge_at = charge_at
        subscription.save(update_fields=[
            'plan',
            'billing_cycle',
            'billing_months',
            'razorpay_payment_reference',
            'status',
            'start_at',
            'current_period_start',
            'current_period_end',
            'charge_at',
            'updated_at',
        ])
    return record


def platform_root_domain():
    configured = getattr(settings, 'TENANT_PLATFORM_ROOT_DOMAIN', '').strip().lower()
    if configured:
        return configured
    parsed = urlparse(settings.SITE_BASE_URL)
    host = (parsed.netloc or parsed.path).split(':', 1)[0].strip().lower()
    parts = host.split('.')
    if len(parts) > 2:
        return '.'.join(parts[-2:])
    return host


def platform_domain_for_name(name):
    root_domain = platform_root_domain()
    subdomain = slugify(name or '').strip('-') or 'publication'
    return f'{subdomain}.{root_domain}'


def tenant_public_site_slug(tenant):
    return slugify(tenant.business_name or tenant.publication_name or tenant.slug).strip('-') or tenant.slug


def tenant_public_site_url(tenant):
    primary_domain = tenant.domains.filter(is_primary=True, status=TenantDomain.Status.ACTIVE).first()
    if primary_domain:
        return f"https://{primary_domain.domain}/"
    return f"{settings.SITE_BASE_URL}/site/{tenant_public_site_slug(tenant)}/"


def ensure_platform_domain_for_tenant(tenant):
    primary = TenantDomain.objects.filter(tenant=tenant, is_primary=True).first()
    if primary:
        return primary
    root_domain = platform_root_domain()
    base_subdomain = slugify(tenant.business_name or tenant.publication_name or tenant.slug).strip('-') or tenant.slug
    for index in range(1, 1000):
        subdomain = base_subdomain if index == 1 else f'{base_subdomain}-{index}'
        domain_name = f'{subdomain}.{root_domain}'
        existing = TenantDomain.objects.filter(domain=domain_name).first()
        if existing and existing.tenant_id == tenant.id:
            if not existing.is_primary or not existing.is_verified or existing.status != TenantDomain.Status.ACTIVE:
                existing.is_primary = True
                existing.is_verified = True
                existing.status = TenantDomain.Status.ACTIVE
                existing.ssl_status = TenantDomain.SSLStatus.ACTIVE
                existing.save(update_fields=['is_primary', 'is_verified', 'status', 'ssl_status', 'updated_at'])
            return existing
        if not existing:
            return TenantDomain.objects.create(
                tenant=tenant,
                domain=domain_name,
                domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN,
                is_primary=True,
                is_verified=True,
                status=TenantDomain.Status.ACTIVE,
                ssl_status=TenantDomain.SSLStatus.ACTIVE,
            )
    raise ValidationError('Unable to create a unique platform domain for this tenant.')


def _append_issue(issues, code, message, fixed=False):
    issues.append({'code': code, 'message': message, 'fixed': fixed})


def _tenant_display_name(tenant):
    return tenant.business_name or tenant.publication_name or tenant.slug


def _tenant_contact_lines(tenant):
    lines = []
    if tenant.email:
        lines.append(f'<li>Email: {tenant.email}</li>')
    if tenant.mobile:
        lines.append(f'<li>Mobile: {tenant.mobile}</li>')
    return ''.join(lines) or '<li>Contact details will be updated by the publication team.</li>'


def _safe_page_content(tenant, title):
    site_name = _tenant_display_name(tenant)
    publication = tenant.publication_name or site_name
    content_map = {
        'about-us': f'''
            <h2>About {publication}</h2>
            <p>{publication} is a digital news publication operated by {site_name}. We publish verified news, public-interest updates, local stories, and useful information for our readers.</p>
            <p>Our newsroom works to keep information clear, responsible, and relevant to the audience served by this website.</p>
        ''',
        'privacy-policy': f'''
            <h2>Privacy Policy</h2>
            <p>{publication} respects reader privacy. We collect basic information only when readers register, contact us, comment, subscribe, or use website features.</p>
            <p>Information may be used to manage accounts, improve services, respond to requests, send updates, protect the website, and meet legal requirements.</p>
            <p>We do not sell personal information. Third-party tools such as analytics, hosting, payment, or communication providers may process data only for website operations.</p>
        ''',
        'terms': f'''
            <h2>Terms and Conditions</h2>
            <p>By using {publication}, readers agree to access the website lawfully and respectfully. Content is provided for news and information purposes.</p>
            <p>Readers must not misuse website features, copy content without permission, or publish abusive, misleading, or unlawful material through this platform.</p>
        ''',
        'disclaimer': f'''
            <h2>Disclaimer</h2>
            <p>{publication} publishes information in good faith and aims for accuracy. News, opinions, third-party links, and public updates may change over time.</p>
            <p>Readers should verify critical information from official sources before making legal, financial, medical, or safety decisions.</p>
        ''',
        'editorial-policy': f'''
            <h2>Editorial Policy</h2>
            <p>{publication} follows an editorial process focused on accuracy, fairness, public interest, and responsible reporting.</p>
            <p>Reports should be checked before publication, headlines should reflect the story, and sponsored or promotional content should be identified clearly when applicable.</p>
        ''',
        'corrections-policy': f'''
            <h2>Corrections Policy</h2>
            <p>If a published story contains an error, {publication} may update, correct, clarify, or remove the content after review.</p>
            <p>Readers can contact the publication team with the story link, correction details, and supporting information.</p>
        ''',
        'ethics-policy': f'''
            <h2>Ethics Policy</h2>
            <p>{publication} expects contributors to avoid plagiarism, undisclosed conflicts of interest, hate speech, harassment, and knowingly false information.</p>
            <p>Editorial decisions should remain independent and should prioritize reader trust and public-interest journalism.</p>
        ''',
        'advertise': f'''
            <h2>Advertise With Us</h2>
            <p>Businesses, organizations, and agencies can contact {publication} for advertising, sponsored content, or partnership opportunities.</p>
            <ul>{_tenant_contact_lines(tenant)}</ul>
        ''',
        'contact-us': f'''
            <h2>Contact {publication}</h2>
            <p>For newsroom queries, corrections, advertising, or support, please contact the publication team.</p>
            <ul>{_tenant_contact_lines(tenant)}</ul>
        ''',
    }
    return ' '.join(content_map.get(slugify(title), f'<p>{publication} will update this {title.lower()} page from the dashboard.</p>').split())


def required_tenant_pages():
    return [
        (Page.PageType.ABOUT, 'About Us', 'about-us', 10),
        (Page.PageType.CONTACT, 'Contact Us', 'contact-us', 20),
        (Page.PageType.PRIVACY, 'Privacy Policy', 'privacy-policy', 30),
        (Page.PageType.TERMS, 'Terms and Conditions', 'terms', 40),
        (Page.PageType.DISCLAIMER, 'Disclaimer', 'disclaimer', 50),
        (Page.PageType.EDITORIAL_POLICY, 'Editorial Policy', 'editorial-policy', 60),
        (Page.PageType.CORRECTIONS_POLICY, 'Corrections Policy', 'corrections-policy', 70),
        (Page.PageType.ETHICS_POLICY, 'Ethics Policy', 'ethics-policy', 80),
        (Page.PageType.ADVERTISE, 'Advertise With Us', 'advertise', 90),
    ]


def ensure_required_tenant_pages(*, tenant):
    footer_menu, _ = Menu.objects.get_or_create(
        tenant=tenant,
        location=Menu.Location.FOOTER,
        defaults={'name': 'Footer Menu'},
    )
    pages = []
    for page_type, title, slug, order in required_tenant_pages():
        page, created = Page.objects.get_or_create(
            tenant=tenant,
            slug=slug,
            defaults={
                'title': title,
                'page_type': page_type,
                'content': _safe_page_content(tenant, slug),
                'is_published': True,
                'seo_title': f'{title} - {_tenant_display_name(tenant)}',
                'meta_description': f'{title} for {_tenant_display_name(tenant)}.',
            },
        )
        update_fields = []
        if not created:
            if not page.is_published:
                page.is_published = True
                update_fields.append('is_published')
            if not page.content.strip():
                page.content = _safe_page_content(tenant, slug)
                update_fields.append('content')
            if not page.seo_title:
                page.seo_title = f'{page.title} - {_tenant_display_name(tenant)}'
                update_fields.append('seo_title')
            if not page.meta_description:
                page.meta_description = f'{page.title} for {_tenant_display_name(tenant)}.'
                update_fields.append('meta_description')
            if update_fields:
                page.save(update_fields=update_fields + ['updated_at'])
        pages.append(page)
        MenuItem.objects.update_or_create(
            tenant=tenant,
            menu=footer_menu,
            page=page,
            defaults={
                'label': title,
                'link_type': MenuItem.LinkType.PAGE,
                'order': order,
                'is_enabled': True,
            },
        )
    return pages


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

    for page_type, title, slug, _order in required_tenant_pages():
        page = Page.objects.filter(tenant=tenant, slug=slug).first()
        if page is None:
            if fix:
                Page.objects.create(
                    tenant=tenant,
                    slug=slug,
                    title=title,
                    page_type=page_type,
                    content=_safe_page_content(tenant, slug),
                    is_published=True,
                )
            _append_issue(issues, f'missing_{page_type}_page', f'{title} page was missing.', fix)
        elif fix and not page.is_published:
            page.is_published = True
            page.save(update_fields=['is_published', 'updated_at'])
            _append_issue(issues, f'unpublished_{page_type}_page', f'{title} page was unpublished.', True)
        elif not page.is_published:
            _append_issue(issues, f'unpublished_{page_type}_page', f'{title} page was unpublished.', False)
    if fix:
        ensure_required_tenant_pages(tenant=tenant)

    get_effective_entitlements(tenant)
    return issues


def verify_razorpay_signature(*, body, signature, secret):
    expected = hmac.new(secret.encode('utf-8'), body, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ''):
        raise ValidationError("Invalid Razorpay signature.")
    return True


def record_purchase_agreement_acceptance(*, user, acquisition, agreement=None, request=None):
    default_title = 'Plan Purchase Agreement'
    default_content = 'User confirmed the plan purchase terms before continuing to payment.'
    default_checkbox_label = 'I have read and agree to the plan purchase terms.'
    ip_address = None
    user_agent = ''
    if request is not None:
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip_address = (forwarded_for.split(',', 1)[0] or request.META.get('REMOTE_ADDR') or '').strip() or None
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:1000]
    return PurchaseAgreementAcceptance.objects.create(
        user=user,
        acquisition=acquisition,
        agreement=agreement,
        agreement_title=agreement.title if agreement else default_title,
        agreement_content=agreement.content if agreement else default_content,
        checkbox_label=agreement.checkbox_label if agreement else default_checkbox_label,
        plan_name=acquisition.plan_price.plan.name if acquisition.plan_price_id else '',
        billing_months=acquisition.billing_months,
        ip_address=ip_address,
        user_agent=user_agent,
        accepted_at=timezone.now(),
    )


def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ValidationError("Razorpay keys are not configured.")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_razorpay_order_for_acquisition(acquisition):
    price = acquisition.plan_price
    checkout_pricing = calculate_checkout_pricing(price, acquisition.billing_months)
    client = get_razorpay_client()
    receipt = f"tenant_{acquisition.user_id}_{acquisition.uuid.hex[:24]}"
    order = client.order.create(
        {
            'amount': checkout_pricing.payable_amount,
            'currency': price.currency,
            'receipt': receipt,
            'payment_capture': 1,
            'notes': {
                'acquisition_uuid': str(acquisition.uuid),
                'publication_slug': acquisition.publication_slug,
                'plan_price_id': str(price.id),
                'plan_code': price.plan.code,
                'billing_cycle': price.billing_cycle,
                'billing_months': str(checkout_pricing.billing_months),
                'list_amount': str(checkout_pricing.list_amount),
                'discount_percent': str(checkout_pricing.discount_percent),
                'discount_amount': str(checkout_pricing.discount_amount),
                'payable_amount': str(checkout_pricing.payable_amount),
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
        'description': f"{price.plan.name} - {checkout_pricing.billing_label}",
        'pricing': {
            'billing_months': checkout_pricing.billing_months,
            'billing_label': checkout_pricing.billing_label,
            'list_amount': checkout_pricing.list_amount,
            'list_display': money_display(checkout_pricing.list_amount, checkout_pricing.currency),
            'discount_percent': checkout_pricing.discount_percent,
            'discount_amount': checkout_pricing.discount_amount,
            'discount_display': money_display(checkout_pricing.discount_amount, checkout_pricing.currency),
            'payable_amount': checkout_pricing.payable_amount,
            'payable_display': money_display(checkout_pricing.payable_amount, checkout_pricing.currency),
        },
        'prefill': {
            'name': acquisition.publication_name,
            'email': acquisition.email,
            'contact': acquisition.mobile,
        },
    }


def create_razorpay_order_for_plan_change(plan_change):
    if plan_change.payable_amount <= 0:
        return {
            'key_id': settings.RAZORPAY_KEY_ID,
            'order_id': '',
            'amount': 0,
            'currency': plan_change.currency,
            'name': 'Press Nexa',
            'description': f"{plan_change.to_plan.name} - {plan_change.billing_months} month{'s' if plan_change.billing_months != 1 else ''}",
            'pricing': _plan_change_pricing_payload(plan_change),
        }
    client = get_razorpay_client()
    receipt = f"upgrade_{plan_change.tenant_id}_{plan_change.uuid.hex[:22]}"
    order = client.order.create(
        {
            'amount': plan_change.payable_amount,
            'currency': plan_change.currency,
            'receipt': receipt,
            'payment_capture': 1,
            'notes': {
                'plan_change_uuid': str(plan_change.uuid),
                'tenant_id': str(plan_change.tenant_id),
                'from_plan': plan_change.from_plan.code,
                'to_plan': plan_change.to_plan.code,
                'billing_months': str(plan_change.billing_months),
                'list_amount': str(plan_change.list_amount),
                'discount_percent': str(plan_change.discount_percent),
                'discount_amount': str(plan_change.discount_amount),
                'credit_amount': str(plan_change.credit_amount),
                'payable_amount': str(plan_change.payable_amount),
            },
        }
    )
    plan_change.provider_order_id = order['id']
    plan_change.provider_payload = {
        **(plan_change.provider_payload or {}),
        'order': order,
        'created_by': 'upgrade_plan',
    }
    plan_change.save(update_fields=['provider_order_id', 'provider_payload', 'updated_at'])
    return {
        'key_id': settings.RAZORPAY_KEY_ID,
        'order_id': order['id'],
        'amount': order['amount'],
        'currency': order['currency'],
        'name': 'Press Nexa',
        'description': f"{plan_change.to_plan.name} - {plan_change.billing_months} month{'s' if plan_change.billing_months != 1 else ''}",
        'pricing': _plan_change_pricing_payload(plan_change),
    }


def _plan_change_pricing_payload(plan_change):
    billing_label = '1 month' if plan_change.billing_months == 1 else f'{plan_change.billing_months} months'
    return {
        'billing_label': billing_label,
        'list_display': money_display(plan_change.list_amount, plan_change.currency),
        'discount_percent': plan_change.discount_percent,
        'discount_display': money_display(plan_change.discount_amount, plan_change.currency),
        'credit_display': money_display(plan_change.credit_amount, plan_change.currency),
        'payable_display': money_display(plan_change.payable_amount, plan_change.currency),
    }


@transaction.atomic
def create_plan_change_checkout(*, tenant, subscription, plan_price, billing_months, requested_by):
    subscription = TenantSubscription.objects.select_for_update().select_related('plan').get(pk=subscription.pk)
    quote = calculate_plan_change_quote(
        tenant=tenant,
        subscription=subscription,
        plan_price=plan_price,
        billing_months=billing_months,
    )
    current_price = monthly_price_for_plan(subscription.plan)
    change_type = PlanChangeRequest.ChangeType.UPGRADE
    if current_price and plan_price.amount < current_price.amount:
        change_type = PlanChangeRequest.ChangeType.DOWNGRADE
    plan_change = PlanChangeRequest.objects.create(
        tenant=tenant,
        from_plan=subscription.plan,
        to_plan=plan_price.plan,
        requested_by=requested_by,
        change_type=change_type,
        status=PlanChangeRequest.Status.PENDING_PAYMENT,
        effective_at=quote['period_start'],
        plan_price=plan_price,
        billing_months=quote['billing_months'],
        list_amount=quote['list_amount'],
        discount_percent=quote['discount_percent'],
        discount_amount=quote['discount_amount'],
        credit_amount=quote['credit_amount'],
        payable_amount=quote['payable_amount'],
        currency=quote['currency'],
        period_start=quote['period_start'],
        period_end=quote['period_end'],
        provider_payload={
            'quote': {
                'remaining_days': quote['remaining_days'],
                'total_days': quote['total_days'],
            },
        },
    )
    checkout = create_razorpay_order_for_plan_change(plan_change)
    return plan_change, checkout


@transaction.atomic
def apply_verified_plan_change_checkout(*, plan_change, provider_order_id='', payment_reference='', provider_signature='', provider_payload=None):
    plan_change = (
        PlanChangeRequest.objects
        .select_for_update()
        .select_related('tenant', 'plan_price__plan', 'to_plan')
        .get(pk=plan_change.pk)
    )
    if plan_change.status == PlanChangeRequest.Status.APPLIED:
        return plan_change
    subscription = TenantSubscription.objects.select_for_update().get(tenant=plan_change.tenant)
    payment_id = payment_reference or provider_order_id or plan_change.provider_order_id
    record_successful_subscription_payment(
        tenant=plan_change.tenant,
        subscription=subscription,
        plan_price=plan_change.plan_price,
        billing_months=plan_change.billing_months,
        provider_order_id=provider_order_id or plan_change.provider_order_id,
        payment_reference=payment_id,
        provider_signature=provider_signature,
        amount=plan_change.payable_amount,
        list_amount=plan_change.list_amount,
        discount_percent=plan_change.discount_percent,
        discount_amount=plan_change.discount_amount + plan_change.credit_amount,
        period_start=plan_change.period_start,
        provider_payload={
            **(provider_payload or {}),
            'plan_change_uuid': str(plan_change.uuid),
            'credit_amount': plan_change.credit_amount,
            'base_offer_discount_amount': plan_change.discount_amount,
            'source': 'upgrade_plan',
        },
    )
    plan_change.provider_order_id = provider_order_id or plan_change.provider_order_id
    plan_change.provider_payment_id = payment_id
    plan_change.provider_reference = payment_id
    plan_change.provider_signature = provider_signature
    plan_change.provider_payload = {
        **(plan_change.provider_payload or {}),
        'verified_checkout': provider_payload or {},
    }
    plan_change.status = PlanChangeRequest.Status.APPLIED
    plan_change.effective_at = timezone.now()
    plan_change.save(update_fields=[
        'provider_order_id',
        'provider_payment_id',
        'provider_reference',
        'provider_signature',
        'provider_payload',
        'status',
        'effective_at',
        'updated_at',
    ])
    get_effective_entitlements(plan_change.tenant)
    return plan_change


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
def _checkout_session_for_acquisition(acquisition):
    pricing = calculate_checkout_pricing(acquisition.plan_price, acquisition.billing_months)
    return {
        'acquisition_id': str(acquisition.id),
        'plan_id': acquisition.plan_price.plan_id,
        'billing_cycle': acquisition.plan_price.billing_cycle,
        'billing_months': pricing.billing_months,
        'amount': pricing.payable_amount,
        'currency': acquisition.plan_price.currency,
        'environment': settings.RAZORPAY_ENVIRONMENT,
    }


def _pricing_defaults(plan_price, billing_months):
    pricing = calculate_checkout_pricing(plan_price, billing_months)
    return {
        'billing_months': pricing.billing_months,
        'list_amount': pricing.list_amount,
        'discount_percent': pricing.discount_percent,
        'discount_amount': pricing.discount_amount,
        'payable_amount': pricing.payable_amount,
    }


def reserve_customer_acquisition(*, business_name, publication_name, publication_slug, email, mobile, password, plan_price, billing_months=1):
    User = get_user_model()
    username = generate_customer_username(publication_name=publication_name, mobile=mobile)
    user = User.objects.create_user(username=username, email=email, password=password)
    pricing_defaults = _pricing_defaults(plan_price, billing_months)
    acquisition = CustomerAcquisition.objects.create(
        user=user,
        plan_price=plan_price,
        business_name=business_name,
        publication_name=publication_name,
        publication_slug=publication_slug,
        email=email,
        mobile=mobile,
        status=CustomerAcquisition.Status.PAYMENT_PENDING,
        **pricing_defaults,
    )
    return acquisition, _checkout_session_for_acquisition(acquisition)


@transaction.atomic
def reserve_customer_acquisition_for_user(*, user, business_name, publication_name, publication_slug, email, mobile, plan_price, billing_months=1):
    pricing_defaults = _pricing_defaults(plan_price, billing_months)
    acquisition = CustomerAcquisition.objects.create(
        user=user,
        plan_price=plan_price,
        business_name=business_name,
        publication_name=publication_name,
        publication_slug=publication_slug,
        email=email or user.email,
        mobile=mobile,
        status=CustomerAcquisition.Status.PAYMENT_PENDING,
        **pricing_defaults,
    )
    return acquisition, _checkout_session_for_acquisition(acquisition)


@transaction.atomic
def update_pending_customer_acquisition(*, acquisition, business_name, publication_name, publication_slug, email, mobile, plan_price, billing_months=1):
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
    pricing_defaults = _pricing_defaults(plan_price, billing_months)
    for field, value in pricing_defaults.items():
        setattr(acquisition, field, value)
    acquisition.save(
        update_fields=[
            'plan_price',
            'business_name',
            'publication_name',
            'publication_slug',
            'email',
            'mobile',
            'provider_order_id',
            'billing_months',
            'list_amount',
            'discount_percent',
            'discount_amount',
            'payable_amount',
            'updated_at',
        ]
    )
    return acquisition, _checkout_session_for_acquisition(acquisition)


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
        ensure_required_tenant_pages(tenant=acquisition.tenant)
        return acquisition.tenant

    checkout_pricing = calculate_checkout_pricing(acquisition.plan_price, acquisition.billing_months)
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
    subscription, _ = TenantSubscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            'plan': acquisition.plan_price.plan,
            'billing_cycle': acquisition.plan_price.billing_cycle,
            'billing_months': acquisition.billing_months,
            'razorpay_payment_reference': payment_reference or provider_order_id,
            'status': TenantSubscription.Status.ACTIVE,
        },
    )
    record_successful_subscription_payment(
        tenant=tenant,
        subscription=subscription,
        plan_price=acquisition.plan_price,
        billing_months=acquisition.billing_months,
        provider_order_id=provider_order_id,
        payment_reference=payment_reference,
        provider_signature=provider_signature,
        amount=acquisition.payable_amount or checkout_pricing.payable_amount,
        list_amount=acquisition.list_amount or checkout_pricing.list_amount,
        discount_percent=acquisition.discount_percent or checkout_pricing.discount_percent,
        discount_amount=acquisition.discount_amount or checkout_pricing.discount_amount,
        provider_payload={
            **(provider_payload or {}),
            'acquisition_uuid': str(acquisition.uuid),
        },
    )
    from .models import TenantOnboarding

    now = timezone.now()
    onboarding, _ = TenantOnboarding.objects.get_or_create(
        tenant=tenant,
        defaults={
            'status': TenantOnboarding.Status.ONBOARDING,
            'site_title': tenant.business_name,
            'organization_name': tenant.business_name,
            'tagline': f'{tenant.business_name} digital newsroom',
            'meta_description': f'{tenant.business_name} publishes news, updates, videos, and public-interest stories.',
        },
    )
    onboarding_update_fields = []
    onboarding_defaults = {
        'site_title': tenant.business_name,
        'organization_name': tenant.business_name,
        'tagline': onboarding.tagline or f'{tenant.business_name} digital newsroom',
        'meta_description': onboarding.meta_description or f'{tenant.business_name} publishes news, updates, videos, and public-interest stories.',
    }
    for field, value in onboarding_defaults.items():
        if value and getattr(onboarding, field) != value:
            setattr(onboarding, field, value)
            onboarding_update_fields.append(field)
    if onboarding_update_fields:
        onboarding_update_fields.append('updated_at')
        onboarding.save(update_fields=onboarding_update_fields)
    ensure_required_tenant_pages(tenant=tenant)
    submit_onboarding_after_payment(onboarding=onboarding, actor=acquisition.user, now=now)
    policy = active_onboarding_policy()
    if policy.mode == OnboardingAutomationPolicy.Mode.INSTANT:
        auto_approve_and_publish_onboarding(
            onboarding=onboarding,
            actor=acquisition.user,
            notes='Auto-approved and published after verified subscription payment.',
            now=now,
        )
    elif policy.mode == OnboardingAutomationPolicy.Mode.DELAYED:
        onboarding.reviewer_notes = f'Auto-publish scheduled after {policy.delay_minutes} minutes if no manual admin action is needed.'
        onboarding.save(update_fields=['reviewer_notes', 'updated_at'])
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
    ensure_platform_domain_for_tenant(tenant)
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
    if action == OnboardingReviewEvent.Action.PUBLISHED:
        ensure_required_tenant_pages(tenant=onboarding.tenant)
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
    ensure_required_tenant_pages(tenant=onboarding.tenant)
    return onboarding


def auto_publish_paid_onboardings(*, older_than_minutes=None, limit=100):
    policy = active_onboarding_policy()
    if policy.mode == OnboardingAutomationPolicy.Mode.MANUAL:
        return []
    if policy.mode == OnboardingAutomationPolicy.Mode.INSTANT:
        older_than_minutes = 0 if older_than_minutes is None else older_than_minutes
    else:
        older_than_minutes = policy.delay_minutes if older_than_minutes is None else older_than_minutes
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
