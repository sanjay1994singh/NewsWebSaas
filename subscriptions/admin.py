from django.contrib import admin

from .pricing import money_display
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
    list_display = ('publication_name', 'user', 'plan_price', 'status', 'tenant', 'provider_order_id', 'provider_payment_id', 'created_at')
    list_filter = ('status', 'plan_price__billing_cycle')
    search_fields = ('publication_name', 'publication_slug', 'business_name', 'email', 'provider_order_id', 'provider_payment_id', 'provider_receipt')
    autocomplete_fields = ('user', 'plan_price', 'tenant')


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
    list_display = ('tenant', 'change_type', 'from_plan', 'to_plan', 'status', 'effective_at', 'created_at')
    list_filter = ('change_type', 'status')
    search_fields = ('tenant__publication_name', 'tenant__slug', 'provider_reference', 'notes')
    autocomplete_fields = ('tenant', 'from_plan', 'to_plan', 'requested_by')


@admin.register(BillingRecord)
class BillingRecordAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'status', 'amount_display', 'currency', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_invoice_id', 'created_at')
    list_filter = ('status', 'currency')
    search_fields = ('tenant__publication_name', 'tenant__slug', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_invoice_id')
    autocomplete_fields = ('tenant', 'subscription')
    readonly_fields = ('entitlement_snapshot',)

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return money_display(obj.amount, obj.currency)


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
