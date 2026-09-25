import base64
from io import BytesIO

from django.contrib import admin, messages
from django.utils.html import format_html

from .pricing import money_display
from .services import create_razorpay_payment_link_for_acquisition, create_razorpay_payment_qr_for_acquisition
from .models import (
    AddOn,
    BillingRecord,
    CustomerAcquisition,
    Feature,
    Plan,
    PlanChangeRequest,
    PlanFeature,
    PlanPrice,
    PlatformPolicy,
    PlatformPurchaseAgreement,
    PlatformSupportContact,
    PurchaseAgreementAcceptance,
    TenantAddOn,
    TenantFeatureOverride,
    TenantOnboarding,
    TenantSubscription,
    OnboardingReviewEvent,
    OnboardingAutomationPolicy,
    WebhookEvent,
)


class PlanPriceInline(admin.TabularInline):
    model = PlanPrice
    extra = 0


class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 0
    autocomplete_fields = ('feature',)


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category', 'feature_type', 'is_active', 'is_public', 'display_order')
    list_filter = ('category', 'feature_type', 'is_active', 'is_public')
    search_fields = ('name', 'code', 'description')
    ordering = ('display_order', 'category', 'name')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'version', 'is_current_version', 'is_active')
    list_filter = ('is_active', 'is_current_version')
    search_fields = ('name', 'code')
    inlines = (PlanPriceInline, PlanFeatureInline)


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ('plan', 'feature', 'is_enabled', 'limit_value', 'updated_at')
    list_filter = ('is_enabled', 'feature__category', 'feature__feature_type')
    search_fields = ('plan__name', 'plan__code', 'feature__name', 'feature__code')
    autocomplete_fields = ('plan', 'feature')


@admin.register(AddOn)
class AddOnAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'feature', 'is_active', 'limit_value')
    list_filter = ('is_active', 'feature__category')
    search_fields = ('name', 'code', 'feature__name', 'feature__code')
    autocomplete_fields = ('feature',)


@admin.register(TenantAddOn)
class TenantAddOnAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'add_on', 'status', 'quantity', 'is_active', 'starts_at', 'ends_at', 'renews_at')
    list_filter = ('status', 'is_active', 'add_on__feature__category')
    search_fields = ('tenant__publication_name', 'tenant__slug', 'add_on__name', 'add_on__code')
    autocomplete_fields = ('tenant', 'add_on')


@admin.register(TenantFeatureOverride)
class TenantFeatureOverrideAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'feature', 'override_type', 'is_enabled', 'limit_value', 'starts_at', 'expires_at')
    list_filter = ('override_type', 'is_enabled', 'feature__category')
    search_fields = ('tenant__publication_name', 'tenant__slug', 'feature__name', 'feature__code', 'reason')
    autocomplete_fields = ('tenant', 'feature', 'created_by')


@admin.register(PlanPrice)
class PlanPriceAdmin(admin.ModelAdmin):
    list_display = ('plan', 'billing_cycle', 'amount_display', 'currency', 'is_active')
    list_filter = ('billing_cycle', 'currency', 'is_active')
    search_fields = ('plan__name', 'plan__code', 'currency')

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return money_display(obj.amount, obj.currency)


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'plan', 'status', 'billing_cycle', 'current_period_end', 'entitlement_snapshot_at')
    list_filter = ('status', 'billing_cycle')
    search_fields = ('tenant__publication_name', 'razorpay_payment_reference')
    autocomplete_fields = ('tenant', 'plan')
    readonly_fields = ('entitlement_snapshot_at',)


@admin.register(CustomerAcquisition)
class CustomerAcquisitionAdmin(admin.ModelAdmin):
    list_display = ('publication_name', 'user', 'plan_price', 'status', 'tax_amount_display', 'payable_amount_display', 'tenant', 'payment_link_anchor', 'payment_qr_anchor', 'provider_order_id', 'provider_payment_id', 'created_at')
    list_filter = ('status', 'plan_price__billing_cycle')
    search_fields = ('publication_name', 'publication_slug', 'business_name', 'email', 'provider_order_id', 'provider_payment_id', 'provider_receipt', 'provider_payment_link_id', 'provider_payment_link_url', 'provider_payment_qr_id', 'provider_payment_qr_url')
    autocomplete_fields = ('user', 'plan_price', 'tenant')
    readonly_fields = ('payment_link_anchor', 'payment_link_qr', 'payment_qr_anchor', 'payment_qr_image')
    actions = ('generate_payment_links', 'generate_payment_qrs')

    @admin.display(description='GST')
    def tax_amount_display(self, obj):
        return money_display(obj.tax_amount, obj.plan_price.currency if obj.plan_price_id else 'INR')

    @admin.display(description='Payable')
    def payable_amount_display(self, obj):
        return money_display(obj.payable_amount, obj.plan_price.currency if obj.plan_price_id else 'INR')

    @admin.display(description='Payment link')
    def payment_link_anchor(self, obj):
        if not obj.provider_payment_link_url:
            return '-'
        return format_html('<a href="{}" target="_blank" rel="noopener">Open payment link</a>', obj.provider_payment_link_url)


    @admin.display(description='Payment QR')
    def payment_link_qr(self, obj):
        if not obj.provider_payment_link_url:
            return '-'
        try:
            import qrcode
        except ImportError:
            return 'Install qrcode[pil] to render QR codes in admin.'
        image = qrcode.make(obj.provider_payment_link_url)
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        return format_html('<img src="data:image/png;base64,{}" alt="Payment QR" width="180" height="180">', encoded)

    @admin.display(description='Scan-to-pay QR')
    def payment_qr_anchor(self, obj):
        if not obj.provider_payment_qr_url:
            return '-'
        return format_html('<a href="{}" target="_blank" rel="noopener">Open Razorpay QR</a>', obj.provider_payment_qr_url)

    @admin.display(description='Direct payment QR image')
    def payment_qr_image(self, obj):
        if obj.provider_payment_qr_image_url:
            return format_html('<img src="{}" alt="Direct payment QR" width="220" height="220" style="object-fit:contain">', obj.provider_payment_qr_image_url)
        if obj.provider_payment_qr_url:
            try:
                import qrcode
            except ImportError:
                return 'Install qrcode[pil] to render QR codes in admin.'
            image = qrcode.make(obj.provider_payment_qr_url)
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
            return format_html('<img src="data:image/png;base64,{}" alt="Direct payment QR" width="220" height="220">', encoded)
        return '-'

    @admin.action(description='Generate Razorpay payment link for selected pending acquisitions')
    def generate_payment_links(self, request, queryset):
        created = 0
        skipped = 0
        failed = 0
        for acquisition in queryset.select_related('plan_price__plan', 'user', 'tenant'):
            if acquisition.tenant_id or acquisition.status != CustomerAcquisition.Status.PAYMENT_PENDING:
                skipped += 1
                continue
            if acquisition.provider_payment_link_url:
                skipped += 1
                continue
            try:
                create_razorpay_payment_link_for_acquisition(acquisition)
            except Exception as exc:
                failed += 1
                self.message_user(request, f'{acquisition.publication_name}: {exc}', level=messages.ERROR)
            else:
                created += 1
        if created:
            self.message_user(request, f'{created} payment link(s) generated. Open each Customer Acquisition row to copy/share the link.', level=messages.SUCCESS)
        if skipped:
            self.message_user(request, f'{skipped} record(s) skipped because they are not pending or already have a payment link.', level=messages.WARNING)
        if failed and not created:
            self.message_user(request, 'No payment links were generated.', level=messages.ERROR)


    @admin.action(description='Generate direct Razorpay scan-to-pay QR for selected pending acquisitions')
    def generate_payment_qrs(self, request, queryset):
        created = 0
        skipped = 0
        failed = 0
        for acquisition in queryset.select_related('plan_price__plan', 'user', 'tenant'):
            if acquisition.tenant_id or acquisition.status != CustomerAcquisition.Status.PAYMENT_PENDING:
                skipped += 1
                continue
            if acquisition.provider_payment_qr_id:
                skipped += 1
                continue
            try:
                create_razorpay_payment_qr_for_acquisition(acquisition)
            except Exception as exc:
                failed += 1
                self.message_user(request, f'{acquisition.publication_name}: {exc}', level=messages.ERROR)
            else:
                created += 1
        if created:
            self.message_user(request, f'{created} scan-to-pay QR code(s) generated. Open each Customer Acquisition row to share the QR image.', level=messages.SUCCESS)
        if skipped:
            self.message_user(request, f'{skipped} record(s) skipped because they are not pending or already have a direct QR.', level=messages.WARNING)
        if failed and not created:
            self.message_user(request, 'No QR codes were generated.', level=messages.ERROR)

class OnboardingReviewEventInline(admin.TabularInline):
    model = OnboardingReviewEvent
    extra = 0
    autocomplete_fields = ('actor',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TenantOnboarding)
class TenantOnboardingAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'status', 'submitted_at', 'reviewed_at', 'published_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('tenant__publication_name', 'tenant__slug', 'site_title', 'organization_name')
    autocomplete_fields = ('tenant',)
    inlines = (OnboardingReviewEventInline,)


@admin.register(OnboardingReviewEvent)
class OnboardingReviewEventAdmin(admin.ModelAdmin):
    list_display = ('onboarding', 'action', 'actor', 'created_at')
    list_filter = ('action',)
    search_fields = ('onboarding__tenant__publication_name', 'notes')
    autocomplete_fields = ('onboarding', 'actor')


@admin.register(OnboardingAutomationPolicy)
class OnboardingAutomationPolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'mode', 'delay_minutes', 'is_active', 'updated_at')
    list_filter = ('mode', 'is_active')
    search_fields = ('name',)


@admin.register(PlanChangeRequest)
class PlanChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'change_type', 'from_plan', 'to_plan', 'status', 'tax_amount_display', 'payable_amount_display', 'effective_at', 'created_at')
    list_filter = ('change_type', 'status')
    search_fields = ('tenant__publication_name', 'tenant__slug', 'provider_reference', 'notes')
    autocomplete_fields = ('tenant', 'from_plan', 'to_plan', 'requested_by')

    @admin.display(description='GST')
    def tax_amount_display(self, obj):
        return money_display(obj.tax_amount, obj.currency)

    @admin.display(description='Payable')
    def payable_amount_display(self, obj):
        return money_display(obj.payable_amount, obj.currency)


@admin.register(BillingRecord)
class BillingRecordAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'status', 'amount_display', 'tax_amount_display', 'currency', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_invoice_id', 'created_at')
    list_filter = ('status', 'currency')
    search_fields = ('tenant__publication_name', 'tenant__slug', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_invoice_id')
    autocomplete_fields = ('tenant', 'subscription')
    readonly_fields = ('entitlement_snapshot',)

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return money_display(obj.amount, obj.currency)

    @admin.display(description='GST')
    def tax_amount_display(self, obj):
        return money_display(obj.tax_amount, obj.currency)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'environment', 'event_id', 'event_type', 'processed_at')
    list_filter = ('provider', 'environment', 'event_type')


@admin.register(PlatformPolicy)
class PlatformPolicyAdmin(admin.ModelAdmin):
    list_display = ('title', 'policy_type', 'is_published', 'updated_at')
    list_filter = ('policy_type', 'is_published')


@admin.register(PlatformSupportContact)
class PlatformSupportContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'support_email', 'whatsapp_number', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'support_email', 'whatsapp_number')


@admin.register(PlatformPurchaseAgreement)
class PlatformPurchaseAgreementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'content', 'checkbox_label')


@admin.register(PurchaseAgreementAcceptance)
class PurchaseAgreementAcceptanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'agreement_title', 'plan_name', 'billing_months', 'accepted_at')
    list_filter = ('agreement', 'billing_months', 'accepted_at')
    search_fields = ('user__username', 'user__email', 'agreement_title', 'agreement_content', 'plan_name')
    autocomplete_fields = ('user', 'acquisition', 'agreement')
    readonly_fields = (
        'user',
        'acquisition',
        'agreement',
        'agreement_title',
        'agreement_content',
        'checkbox_label',
        'plan_name',
        'billing_months',
        'ip_address',
        'user_agent',
        'accepted_at',
        'created_at',
        'updated_at',
    )
