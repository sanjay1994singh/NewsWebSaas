from django.contrib import admin
from django.contrib import messages

from .services import sync_razorpay_plan_for_price

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
    RazorpayPlanMapping,
    TenantAddOn,
    TenantFeatureOverride,
    TenantOnboarding,
    TenantSubscription,
    OnboardingReviewEvent,
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
    list_display = ('plan', 'billing_cycle', 'amount', 'currency', 'is_active')
    list_filter = ('billing_cycle', 'currency', 'is_active')
    search_fields = ('plan__name', 'plan__code', 'currency')
    actions = ('sync_selected_to_razorpay',)

    @admin.action(description='Sync selected prices to Razorpay')
    def sync_selected_to_razorpay(self, request, queryset):
        synced = 0
        failed = 0
        for price in queryset.select_related('plan'):
            try:
                sync_razorpay_plan_for_price(price)
                synced += 1
            except Exception as exc:
                failed += 1
                self.message_user(request, f"{price}: {exc}", level=messages.ERROR)
        if synced:
            self.message_user(request, f"{synced} Razorpay plan mapping(s) ready.", level=messages.SUCCESS)
        if failed:
            self.message_user(request, f"{failed} price(s) could not be synced.", level=messages.WARNING)


@admin.register(RazorpayPlanMapping)
class RazorpayPlanMappingAdmin(admin.ModelAdmin):
    list_display = ('price', 'environment', 'razorpay_plan_id', 'version', 'is_active')
    list_filter = ('environment', 'is_active')
    search_fields = ('price__plan__name', 'price__plan__code', 'razorpay_plan_id')
    autocomplete_fields = ('price',)


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'plan', 'status', 'billing_cycle', 'current_period_end')
    list_filter = ('status', 'billing_cycle')
    search_fields = ('tenant__publication_name', 'razorpay_subscription_id')
    autocomplete_fields = ('tenant', 'plan')


@admin.register(CustomerAcquisition)
class CustomerAcquisitionAdmin(admin.ModelAdmin):
    list_display = ('publication_name', 'user', 'plan_price', 'status', 'tenant', 'provider_subscription_id', 'created_at')
    list_filter = ('status', 'plan_price__billing_cycle')
    search_fields = ('publication_name', 'publication_slug', 'business_name', 'email', 'provider_subscription_id')
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


@admin.register(PlanChangeRequest)
class PlanChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'change_type', 'from_plan', 'to_plan', 'status', 'effective_at', 'created_at')
    list_filter = ('change_type', 'status')
    search_fields = ('tenant__publication_name', 'tenant__slug', 'provider_reference', 'notes')
    autocomplete_fields = ('tenant', 'from_plan', 'to_plan', 'requested_by')


@admin.register(BillingRecord)
class BillingRecordAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'status', 'amount', 'currency', 'razorpay_payment_id', 'razorpay_invoice_id', 'created_at')
    list_filter = ('status', 'currency')
    autocomplete_fields = ('tenant', 'subscription')


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'environment', 'event_id', 'event_type', 'processed_at')
    list_filter = ('provider', 'environment', 'event_type')


@admin.register(PlatformPolicy)
class PlatformPolicyAdmin(admin.ModelAdmin):
    list_display = ('title', 'policy_type', 'is_published', 'updated_at')
    list_filter = ('policy_type', 'is_published')
