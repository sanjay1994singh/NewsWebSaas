from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from core.models import user_can_access_tenant
from tenants.models import Tenant

from .entitlements import get_effective_entitlement, get_effective_entitlements
from .forms import CustomerSignupForm, CustomerWorkspaceForm, OnboardingForm, ReviewActionForm
from .invoices import build_invoice_pdf, email_invoice, invoice_filename
from .models import (
    AddOn,
    BillingRecord,
    CustomerAcquisition,
    Feature,
    OnboardingReviewEvent,
    Plan,
    PlanFeature,
    PlanPrice,
    PlatformPolicy,
    TenantAddOn,
    TenantOnboarding,
    TenantSubscription,
)
from .services import (
    activate_tenant_add_on,
    apply_verified_plan_change,
    create_tenant_after_verified_subscription,
    create_razorpay_order_for_acquisition,
    process_webhook,
    record_onboarding_review,
    request_plan_change,
    reserve_customer_acquisition,
    reserve_customer_acquisition_for_user,
    submit_onboarding_for_review,
    update_pending_customer_acquisition,
    verify_razorpay_checkout_signature,
)
from .whatsapp import notify_payment_failed, notify_payment_success

COMPANY_PROFILE = {
    'brand_name': 'Press Nexa',
    'legal_name': 'SHRI INFOWAVE PRIVATE LIMITED',
    'cin': 'U62012UW2026PTC257361',
    'pan': 'ABUCS7544P',
    'incorporated_on': '17 August 2026',
    'registered_office': '101 Govind Kund Tila, Radha Niwas, Vrindaban, Mathura, Mathura - 281121, Uttar Pradesh, India',
    'support_email': 'srbc500@gmail.com',
    'whatsapp_number': '8279408396',
    'whatsapp_url': 'https://wa.me/918279408396',
    'business_hours': 'Monday to Saturday, 10:00 AM to 6:00 PM IST',
}


def _customer_tenant_context(user):
    if not user.is_authenticated:
        return None, None, None
    tenant = (
        Tenant.objects
        .filter(memberships__user=user, memberships__status='active')
        .select_related('owner')
        .order_by('memberships__role', 'created_at')
        .first()
    )
    if tenant is None:
        tenant = Tenant.objects.filter(owner=user).select_related('owner').first()
    subscription = None
    onboarding_record = None
    if tenant:
        try:
            subscription = tenant.subscription
        except TenantSubscription.DoesNotExist:
            subscription = None
        try:
            onboarding_record = tenant.commercial_onboarding
        except TenantOnboarding.DoesNotExist:
            onboarding_record = None
    return tenant, subscription, onboarding_record


def customer_home(request):
    if not request.user.is_authenticated:
        return landing_page(request)

    tenant, subscription, onboarding_record = _customer_tenant_context(request.user)
    if tenant is None or subscription is None or subscription.status not in {
        subscription.Status.TRIAL,
        subscription.Status.ACTIVE,
        subscription.Status.GRACE_PERIOD,
    }:
        return redirect('subscriptions:account_status')

    if tenant.status in {Tenant.Status.PAST_DUE, Tenant.Status.SUSPENDED, Tenant.Status.CANCELLED, Tenant.Status.EXPIRED}:
        return redirect('subscriptions:account_status')

    if onboarding_record is None:
        return redirect('subscriptions:onboarding')

    if onboarding_record.status in {
        TenantOnboarding.Status.PAYMENT_PENDING,
        TenantOnboarding.Status.ONBOARDING,
        TenantOnboarding.Status.CHANGES_REQUESTED,
    }:
        return redirect('subscriptions:onboarding')

    if onboarding_record.status in {
        TenantOnboarding.Status.SUBMITTED_FOR_REVIEW,
        TenantOnboarding.Status.UNDER_REVIEW,
    }:
        return redirect('subscriptions:review_status')

    if onboarding_record.status in {
        TenantOnboarding.Status.APPROVED,
        TenantOnboarding.Status.READY_TO_PUBLISH,
    }:
        return redirect('subscriptions:ready_to_publish')

    if onboarding_record.status == TenantOnboarding.Status.PUBLISHED:
        _activate_published_tenant(tenant)
        return redirect('tenants:tenant_dashboard')

    return redirect('subscriptions:account_status')


def _public_plan_context():
    plans = (
        Plan.objects
        .filter(is_active=True, is_current_version=True)
        .prefetch_related('prices', 'features__feature')
        .order_by('id')
    )
    features = Feature.objects.filter(is_active=True, is_public=True).order_by('display_order', 'category', 'name')
    plan_features = PlanFeature.objects.select_related('plan', 'feature').filter(
        plan__in=plans,
        feature__in=features,
    )
    feature_matrix = {}
    for feature in features:
        feature_matrix[feature.code] = {'feature': feature, 'plans': {}}
    for plan_feature in plan_features:
        feature_matrix[plan_feature.feature.code]['plans'][plan_feature.plan_id] = plan_feature

    def price_display(price):
        if not price:
            return ''
        amount = price.amount / 100
        amount_text = f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"
        return f"{price.currency} {amount_text}"

    plan_cards = []
    for plan in plans:
        prices = list(plan.prices.all())
        monthly_price = next((price for price in prices if price.billing_cycle == PlanPrice.BillingCycle.MONTHLY), None)
        yearly_price = next((price for price in prices if price.billing_cycle == PlanPrice.BillingCycle.YEARLY), None)
        enabled_features = [
            plan_feature
            for plan_feature in plan.features.all()
            if plan_feature.is_enabled and plan_feature.feature.is_public
        ]
        plan_cards.append(
            {
                'plan': plan,
                'monthly_price': monthly_price,
                'yearly_price': yearly_price,
                'monthly_display': price_display(monthly_price),
                'yearly_display': price_display(yearly_price),
                'enabled_features': enabled_features[:8],
                'signup_price': monthly_price or yearly_price,
            }
        )

    comparison_rows = []
    for row in feature_matrix.values():
        cells = []
        for plan in plans:
            plan_feature = row['plans'].get(plan.id)
            value = 'No'
            enabled = False
            if plan_feature and plan_feature.is_enabled:
                enabled = True
                value = str(plan_feature.limit_value) if plan_feature.limit_value else 'Yes'
            cells.append({'enabled': enabled, 'value': value})
        comparison_rows.append({'feature': row['feature'], 'cells': cells})

    return {'plans': plans, 'plan_cards': plan_cards, 'features': features, 'comparison_rows': comparison_rows}


def _activate_published_tenant(tenant):
    if tenant.status == Tenant.Status.ACTIVE and tenant.onboarding_status == Tenant.OnboardingStatus.COMPLETE:
        return
    tenant.status = Tenant.Status.ACTIVE
    tenant.onboarding_status = Tenant.OnboardingStatus.COMPLETE
    tenant.save(update_fields=['status', 'onboarding_status', 'updated_at'])


def about_us(request):
    return render(
        request,
        'subscriptions/about.html',
        {
            'company': COMPANY_PROFILE,
            'page_title': 'About Press Nexa',
        },
    )


def policy_page(request, policy_type):
    policy = get_object_or_404(PlatformPolicy, policy_type=policy_type, is_published=True)
    return render(
        request,
        'subscriptions/policy_page.html',
        {
            'company': COMPANY_PROFILE,
            'policy': policy,
            'page_title': policy.title,
        },
    )


def landing_page(request):
    context = _public_plan_context()
    context.update(
        {
            'page_title': 'Press Nexa News Publishing Platform',
            'page_description': 'Launch and manage a multi-tenant news website with publishing, video, monetization, subscriptions, and optional ePaper support.',
            'canonical_url': request.build_absolute_uri('/'),
        }
    )
    return render(request, 'subscriptions/landing.html', context)


@require_http_methods(['GET', 'POST'])
def signup(request):
    initial_price_id = request.GET.get('price')
    if request.user.is_authenticated:
        tenant, subscription, onboarding_record = _customer_tenant_context(request.user)
        if tenant and subscription:
            return redirect('home')
        selected_price = None
        if initial_price_id:
            selected_price = PlanPrice.objects.filter(pk=initial_price_id, is_active=True, plan__is_active=True).first()
        if request.method == 'GET' and selected_price:
            pending_acquisition = (
                CustomerAcquisition.objects
                .filter(
                    user=request.user,
                    plan_price=selected_price,
                    tenant__isnull=True,
                    status=CustomerAcquisition.Status.PAYMENT_PENDING,
                )
                .order_by('-created_at')
                .first()
            )
            if pending_acquisition:
                messages.info(request, 'Your workspace details are already saved. Continue the subscription payment to activate it.')
                return redirect('subscriptions:checkout', acquisition_id=pending_acquisition.uuid)
        if request.method == 'POST':
            form = CustomerWorkspaceForm(request.POST, user=request.user)
            if form.is_valid():
                if form.existing_acquisition:
                    acquisition, checkout = update_pending_customer_acquisition(
                        acquisition=form.existing_acquisition,
                        business_name=form.cleaned_data['business_name'],
                        publication_name=form.cleaned_data['publication_name'],
                        publication_slug=form.cleaned_data['publication_slug'],
                        email=form.cleaned_data['email'],
                        mobile=form.cleaned_data['mobile'],
                        plan_price=form.cleaned_data['price_id'],
                    )
                    messages.info(request, 'Your saved workspace details were updated. Continue payment to activate it.')
                else:
                    acquisition, checkout = reserve_customer_acquisition_for_user(
                        user=request.user,
                        business_name=form.cleaned_data['business_name'],
                        publication_name=form.cleaned_data['publication_name'],
                        publication_slug=form.cleaned_data['publication_slug'],
                        email=form.cleaned_data['email'],
                        mobile=form.cleaned_data['mobile'],
                        plan_price=form.cleaned_data['price_id'],
                    )
                    messages.success(request, 'Workspace reserved. Complete the verified subscription step to activate your tenant.')
                request.session['pending_checkout'] = checkout
                return redirect('subscriptions:checkout', acquisition_id=acquisition.uuid)
        else:
            form = CustomerWorkspaceForm(initial={'price_id': initial_price_id}, user=request.user)
        return render(
            request,
            'subscriptions/signup.html',
            {
                'form': form,
                'plans': _public_plan_context()['plans'],
                'is_workspace_flow': True,
            },
        )

    if request.method == 'POST':
        form = CustomerSignupForm(request.POST)
        if form.is_valid():
            acquisition, checkout = reserve_customer_acquisition(
                business_name=form.cleaned_data['business_name'],
                publication_name=form.cleaned_data['publication_name'],
                publication_slug=form.cleaned_data['publication_slug'],
                email=form.cleaned_data['email'],
                mobile=form.cleaned_data['mobile'],
                plan_price=form.cleaned_data['price_id'],
            )
            login(request, acquisition.user)
            request.session['pending_checkout'] = checkout
            messages.success(request, 'Account reserved. Complete the verified subscription step to create your tenant workspace.')
            return redirect('subscriptions:checkout', acquisition_id=acquisition.uuid)
    else:
        form = CustomerSignupForm(initial={'price_id': initial_price_id})
    return render(request, 'subscriptions/signup.html', {'form': form, 'plans': _public_plan_context()['plans']})


@login_required
def checkout(request, acquisition_id):
    acquisition = get_object_or_404(
        CustomerAcquisition.objects.select_related('plan_price__plan', 'tenant'),
        uuid=acquisition_id,
        user=request.user,
    )
    tenant, subscription, onboarding_record = _customer_tenant_context(request.user)
    if acquisition.tenant_id or acquisition.status == CustomerAcquisition.Status.TENANT_CREATED:
        messages.info(request, 'This payment is already verified. Continue from your workspace.')
        return redirect('home')
    if tenant and subscription and subscription.status in {
        TenantSubscription.Status.TRIAL,
        TenantSubscription.Status.ACTIVE,
        TenantSubscription.Status.GRACE_PERIOD,
    }:
        if onboarding_record and onboarding_record.status == TenantOnboarding.Status.PUBLISHED:
            _activate_published_tenant(tenant)
        messages.info(request, 'Your workspace is already active. Continue from your account.')
        return redirect('home')
    if acquisition.status != CustomerAcquisition.Status.PAYMENT_PENDING:
        messages.info(request, 'This payment request is no longer active. Choose a plan to continue.')
        return redirect('subscriptions:account_status')
    checkout_data = request.session.get('pending_checkout', {})
    try:
        checkout_is_stale = (
            checkout_data.get('acquisition_id') != str(acquisition.id)
            or checkout_data.get('amount') != acquisition.plan_price.amount
            or checkout_data.get('currency') != acquisition.plan_price.currency
        )
        if not checkout_data.get('order_id') or checkout_is_stale:
            checkout_data = create_razorpay_order_for_acquisition(acquisition)
            checkout_data['acquisition_id'] = str(acquisition.id)
            request.session['pending_checkout'] = checkout_data
    except ValidationError as exc:
        checkout_data['checkout_error'] = exc.message
    except Exception:
        checkout_data['checkout_error'] = 'Unable to initialize Razorpay checkout right now.'
    return render(request, 'subscriptions/checkout.html', {'acquisition': acquisition, 'checkout': checkout_data})


@login_required
@require_POST
def verify_subscription(request, acquisition_id):
    acquisition = get_object_or_404(CustomerAcquisition.objects.select_related('plan_price__plan'), uuid=acquisition_id, user=request.user)
    order_id = request.POST.get('razorpay_order_id', '').strip()
    payment_id = request.POST.get('razorpay_payment_id', '').strip()
    signature = request.POST.get('razorpay_signature', '').strip()
    if not order_id or not payment_id or not signature:
        messages.error(request, 'Verified Razorpay payment response is required.')
        return redirect('subscriptions:checkout', acquisition_id=acquisition.uuid)
    try:
        verify_razorpay_checkout_signature(
            payment_id=payment_id,
            order_id=order_id,
            signature=signature,
        )
    except ValidationError:
        messages.error(request, 'Razorpay payment signature verification failed.')
        return redirect('subscriptions:checkout', acquisition_id=acquisition.uuid)
    tenant = create_tenant_after_verified_subscription(
        acquisition=acquisition,
        provider_order_id=order_id,
        payment_reference=payment_id,
        provider_signature=signature,
        provider_payload={
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature_present': bool(signature),
            'source': 'checkout_verify',
        },
    )
    billing_record = BillingRecord.objects.filter(tenant=tenant, status='paid').order_by('-created_at').first()
    if billing_record:
        email_invoice(billing_record)
    notify_payment_success(
        acquisition=acquisition,
        tenant=tenant,
        payment_reference=payment_id,
        dashboard_url=request.build_absolute_uri('/dashboard/'),
        profile_url=request.build_absolute_uri('/account/profile/'),
    )
    messages.success(request, 'Subscription verified. Your dashboard is ready. Complete setup details from the dashboard.')
    return redirect('tenants:tenant_dashboard')


@login_required
@require_POST
def payment_failed(request, acquisition_id):
    acquisition = get_object_or_404(CustomerAcquisition.objects.select_related('plan_price__plan', 'user'), uuid=acquisition_id, user=request.user)
    payment_reference = request.POST.get('razorpay_payment_id', '').strip() or request.POST.get('razorpay_order_id', '').strip() or acquisition.provider_order_id
    acquisition.provider_payment_id = request.POST.get('razorpay_payment_id', '').strip()
    acquisition.provider_payload = {
        **(acquisition.provider_payload or {}),
        'failed_checkout': {
            'razorpay_order_id': request.POST.get('razorpay_order_id', '').strip(),
            'razorpay_payment_id': request.POST.get('razorpay_payment_id', '').strip(),
            'source': 'checkout_failed',
        },
    }
    acquisition.status = CustomerAcquisition.Status.FAILED
    acquisition.save(update_fields=['provider_payment_id', 'provider_payload', 'status', 'updated_at'])
    notify_payment_failed(
        acquisition=acquisition,
        payment_reference=payment_reference,
        checkout_url=request.build_absolute_uri(f'/billing/saas/checkout/{acquisition.uuid}/'),
        profile_url=request.build_absolute_uri('/account/profile/'),
    )
    return JsonResponse({'ok': True})


def _owned_tenant_for_user(user):
    tenant, subscription, onboarding_record = _customer_tenant_context(user)
    return tenant


@login_required
@require_http_methods(['GET', 'POST'])
def onboarding(request):
    tenant = _owned_tenant_for_user(request.user)
    if tenant is None:
        messages.error(request, 'No tenant workspace is linked with this account yet.')
        return redirect('subscriptions:landing')
    onboarding_record, _ = TenantOnboarding.objects.get_or_create(
        tenant=tenant,
        defaults={'status': TenantOnboarding.Status.ONBOARDING},
    )
    if onboarding_record.status in {
        TenantOnboarding.Status.SUBMITTED_FOR_REVIEW,
        TenantOnboarding.Status.UNDER_REVIEW,
    }:
        return redirect('subscriptions:review_status')
    if onboarding_record.status in {
        TenantOnboarding.Status.APPROVED,
        TenantOnboarding.Status.READY_TO_PUBLISH,
    }:
        return redirect('subscriptions:ready_to_publish')
    if onboarding_record.status == TenantOnboarding.Status.PUBLISHED:
        _activate_published_tenant(tenant)
        return redirect('tenants:tenant_dashboard')
    if request.method == 'POST':
        form = OnboardingForm(request.POST, request.FILES, instance=onboarding_record)
        if form.is_valid():
            form.save()
            if 'submit_for_review' in request.POST:
                submit_onboarding_for_review(onboarding=onboarding_record, actor=request.user)
                messages.success(request, 'Onboarding submitted for review.')
            else:
                messages.success(request, 'Onboarding saved.')
            return redirect('subscriptions:onboarding')
    else:
        form = OnboardingForm(instance=onboarding_record)
    entitlements = get_effective_entitlements(tenant)
    return render(
        request,
        'subscriptions/onboarding.html',
        {'tenant': tenant, 'onboarding': onboarding_record, 'form': form, 'entitlements': entitlements},
    )


@login_required
def review_status(request):
    tenant = _owned_tenant_for_user(request.user)
    if tenant is None:
        return redirect('subscriptions:account_status')
    onboarding_record, _ = TenantOnboarding.objects.get_or_create(tenant=tenant)
    if onboarding_record.status in {
        TenantOnboarding.Status.APPROVED,
        TenantOnboarding.Status.READY_TO_PUBLISH,
    }:
        return redirect('subscriptions:ready_to_publish')
    if onboarding_record.status == TenantOnboarding.Status.PUBLISHED:
        _activate_published_tenant(tenant)
        return redirect('tenants:tenant_dashboard')
    return render(
        request,
        'subscriptions/review_status.html',
        {'tenant': tenant, 'onboarding': onboarding_record, 'events': onboarding_record.review_events.order_by('-created_at')[:10]},
    )


@login_required
def ready_to_publish(request):
    tenant = _owned_tenant_for_user(request.user)
    if tenant is None:
        return redirect('subscriptions:account_status')
    onboarding_record, _ = TenantOnboarding.objects.get_or_create(tenant=tenant)
    if onboarding_record.status == TenantOnboarding.Status.PUBLISHED:
        _activate_published_tenant(tenant)
        return redirect('tenants:tenant_dashboard')
    entitlements = get_effective_entitlements(tenant)
    return render(
        request,
        'subscriptions/ready_to_publish.html',
        {'tenant': tenant, 'onboarding': onboarding_record, 'entitlements': entitlements},
    )


@staff_member_required
@require_http_methods(['GET', 'POST'])
def onboarding_review(request, onboarding_id):
    onboarding_record = get_object_or_404(TenantOnboarding.objects.select_related('tenant'), pk=onboarding_id)
    if request.method == 'POST':
        form = ReviewActionForm(request.POST)
        if form.is_valid():
            record_onboarding_review(
                onboarding=onboarding_record,
                action=form.cleaned_data['action'],
                actor=request.user,
                notes=form.cleaned_data['notes'],
            )
            messages.success(request, 'Review action recorded.')
            return redirect('subscriptions:onboarding_review', onboarding_id=onboarding_record.id)
    else:
        form = ReviewActionForm()
    entitlements = get_effective_entitlements(onboarding_record.tenant)
    return render(
        request,
        'subscriptions/onboarding_review.html',
        {'onboarding': onboarding_record, 'form': form, 'entitlements': entitlements},
    )


@login_required
def billing_dashboard(request):
    tenant, subscription, onboarding_record = _customer_tenant_context(request.user)
    if tenant is None:
        messages.error(request, 'No tenant workspace is linked with this account yet.')
        return redirect('subscriptions:account_status')
    if subscription and subscription.razorpay_payment_reference:
        plan_price = (
            PlanPrice.objects
            .filter(
                plan=subscription.plan,
                billing_cycle=subscription.billing_cycle,
                is_active=True,
            )
            .first()
        )
        BillingRecord.objects.get_or_create(
            tenant=tenant,
            razorpay_payment_id=subscription.razorpay_payment_reference,
            defaults={
                'subscription': subscription,
                'amount': plan_price.amount if plan_price else 0,
                'currency': plan_price.currency if plan_price else 'INR',
                'status': 'paid',
                'payload': {
                    'source': 'billing_dashboard_backfill',
                    'plan': subscription.plan.name,
                    'billing_cycle': subscription.billing_cycle,
                },
            },
        )
    plans = Plan.objects.filter(is_active=True, is_current_version=True).prefetch_related('prices')
    add_ons = AddOn.objects.filter(is_active=True).select_related('feature').order_by('display_order', 'name')
    entitlements = get_effective_entitlements(tenant)
    invoices = BillingRecord.objects.filter(tenant=tenant).select_related('subscription__plan').order_by('-created_at')[:20]
    return render(
        request,
        'subscriptions/billing_dashboard.html',
        {
            'tenant': tenant,
            'subscription': subscription,
            'onboarding': onboarding_record,
            'plans': plans,
            'add_ons': add_ons,
            'entitlements': entitlements,
            'invoices': invoices,
        },
    )


@login_required
def download_invoice(request, record_id):
    record = get_object_or_404(
        BillingRecord.objects.select_related('tenant', 'subscription__plan'),
        pk=record_id,
    )
    if record.tenant.owner_id != request.user.id and not user_can_access_tenant(request.user, record.tenant):
        raise PermissionDenied("You do not have access to this invoice.")
    response = HttpResponse(build_invoice_pdf(record), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice_filename(record)}"'
    return response


@login_required
def view_invoice(request, record_id):
    record = get_object_or_404(
        BillingRecord.objects.select_related('tenant', 'subscription__plan'),
        pk=record_id,
    )
    if record.tenant.owner_id != request.user.id and not user_can_access_tenant(request.user, record.tenant):
        raise PermissionDenied("You do not have access to this invoice.")
    response = HttpResponse(build_invoice_pdf(record), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{invoice_filename(record)}"'
    return response


@login_required
def account_status(request):
    tenant, subscription, onboarding_record = _customer_tenant_context(request.user)
    plans = _public_plan_context()['plan_cards']
    entitlements = get_effective_entitlements(tenant) if tenant else {}
    return render(
        request,
        'subscriptions/account_status.html',
        {
            'tenant': tenant,
            'subscription': subscription,
            'onboarding': onboarding_record,
            'plans': plans,
            'entitlements': entitlements,
        },
    )


@login_required
@require_POST
def change_plan(request):
    tenant = _owned_tenant_for_user(request.user)
    if tenant is None:
        return JsonResponse({'detail': 'No tenant workspace found.'}, status=404)
    to_plan = get_object_or_404(Plan, pk=request.POST.get('plan_id'), is_active=True)
    plan_change = request_plan_change(tenant=tenant, to_plan=to_plan, requested_by=request.user)
    if request.POST.get('provider_reference'):
        apply_verified_plan_change(plan_change=plan_change, provider_reference=request.POST['provider_reference'])
        messages.success(request, 'Verified plan change applied.')
    else:
        messages.success(request, 'Plan change requested. Paid features unlock only after provider verification.')
    return redirect('subscriptions:billing_dashboard')


@login_required
@require_POST
def activate_add_on(request, add_on_id):
    tenant = _owned_tenant_for_user(request.user)
    if tenant is None:
        return JsonResponse({'detail': 'No tenant workspace found.'}, status=404)
    add_on = get_object_or_404(AddOn, pk=add_on_id, is_active=True)
    tenant_add_on, _ = TenantAddOn.objects.get_or_create(
        tenant=tenant,
        add_on=add_on,
        defaults={'status': TenantAddOn.Status.PAYMENT_PENDING, 'is_active': False},
    )
    provider_payment_reference = request.POST.get('provider_payment_reference', '').strip()
    if provider_payment_reference:
        activate_tenant_add_on(tenant_add_on=tenant_add_on, provider_payment_reference=provider_payment_reference)
        messages.success(request, 'Verified add-on activated.')
    else:
        messages.success(request, 'Add-on reserved. It activates only after provider verification.')
    return redirect('subscriptions:billing_dashboard')


@login_required
@require_POST
def cancel_add_on(request, tenant_add_on_id):
    tenant = _owned_tenant_for_user(request.user)
    tenant_add_on = get_object_or_404(TenantAddOn, pk=tenant_add_on_id, tenant=tenant)
    tenant_add_on.status = TenantAddOn.Status.CANCELLED
    tenant_add_on.is_active = False
    tenant_add_on.save(update_fields=['status', 'is_active', 'updated_at'])
    messages.success(request, 'Add-on cancelled. Existing data is preserved.')
    return redirect('subscriptions:billing_dashboard')


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    try:
        event = process_webhook(
            body=request.body,
            signature=request.headers.get('X-Razorpay-Signature'),
            environment=settings.RAZORPAY_ENVIRONMENT,
        )
    except ValidationError:
        return HttpResponse(status=400)
    return JsonResponse({'processed': bool(event.processed_at), 'event_id': event.event_id})


def feature_access_check(request, tenant_slug, feature_code):
    tenant = get_object_or_404(Tenant, slug=tenant_slug)
    entitlement = get_effective_entitlement(tenant, feature_code)
    if not entitlement['is_enabled']:
        return JsonResponse(
            {'detail': 'This feature is not enabled for the current tenant.'},
            status=403,
        )
    return JsonResponse(
        {
            'tenant': tenant.slug,
            'feature': feature_code,
            'enabled': True,
            'limit': entitlement['limit_value'],
            'source': entitlement['source'],
        }
    )
