from django.conf import settings
from django.db import models

from core.fields import JSONTextField
from core.models import TimeStampedModel, UUIDModel


class Plan(UUIDModel, TimeStampedModel):
    class Code(models.TextChoices):
        STARTER = 'starter', 'Starter'
        PROFESSIONAL = 'professional', 'Professional'
        BUSINESS = 'business', 'Business'
        NEWS_STARTER = 'news_starter', 'News Starter'
        NEWS_VIDEO = 'news_video', 'News + Video'
        NEWS_PRO = 'news_pro', 'News Pro'
        NEWS_BUSINESS = 'news_business', 'News Business'

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, choices=Code.choices)
    version = models.PositiveIntegerField(default=1)
    is_current_version = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    entitlements = JSONTextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['code', 'version'], name='unique_plan_code_version'),
        ]

    def __str__(self):
        return f"{self.name} v{self.version}"


class Feature(UUIDModel, TimeStampedModel):
    class FeatureType(models.TextChoices):
        BOOLEAN = 'boolean', 'Boolean'
        LIMIT = 'limit', 'Limit'
        CONFIGURATION = 'configuration', 'Configuration'

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, db_index=True)
    feature_type = models.CharField(max_length=20, choices=FeatureType.choices, default=FeatureType.BOOLEAN)
    default_unit = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_public = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('display_order', 'category', 'name')

    def __str__(self):
        return self.name


class PlanFeature(TimeStampedModel):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='features')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='plan_features')
    is_enabled = models.BooleanField(default=False)
    limit_value = models.PositiveIntegerField(null=True, blank=True)
    configuration_json = JSONTextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['plan', 'feature'], name='unique_plan_feature'),
        ]
        indexes = [
            models.Index(fields=['plan', 'is_enabled']),
            models.Index(fields=['feature', 'is_enabled']),
        ]

    def __str__(self):
        return f"{self.plan} - {self.feature}"


class AddOn(UUIDModel, TimeStampedModel):
    feature = models.ForeignKey(Feature, on_delete=models.PROTECT, related_name='add_ons')
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    monthly_price = models.PositiveIntegerField(default=0)
    yearly_price = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default='INR')
    razorpay_monthly_plan_id = models.CharField(max_length=120, blank=True)
    razorpay_yearly_plan_id = models.CharField(max_length=120, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    limit_value = models.PositiveIntegerField(null=True, blank=True)
    configuration_json = JSONTextField(blank=True)

    def __str__(self):
        return self.name


class TenantAddOn(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAYMENT_PENDING = 'payment_pending', 'Payment Pending'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='add_ons')
    add_on = models.ForeignKey(AddOn, on_delete=models.PROTECT, related_name='tenant_add_ons')
    provider_subscription_id = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    quantity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    renews_at = models.DateTimeField(null=True, blank=True)
    limit_override = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['starts_at', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.tenant} - {self.add_on}"


class TenantFeatureOverride(TimeStampedModel):
    class OverrideType(models.TextChoices):
        GRANT = 'grant', 'Grant'
        RESTRICT = 'restrict', 'Restrict'
        CONFIGURE = 'configure', 'Configure'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='feature_overrides')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='tenant_overrides')
    override_type = models.CharField(max_length=20, choices=OverrideType.choices)
    is_enabled = models.BooleanField(default=True)
    limit_value = models.PositiveIntegerField(null=True, blank=True)
    configuration_json = JSONTextField(blank=True)
    reason = models.TextField(blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_feature_overrides',
    )

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['tenant', 'feature', 'override_type']),
            models.Index(fields=['starts_at', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.tenant} - {self.feature} ({self.override_type})"


class PlanPrice(TimeStampedModel):
    class BillingCycle(models.TextChoices):
        MONTHLY = 'monthly', 'Monthly'
        YEARLY = 'yearly', 'Yearly'

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='prices')
    billing_cycle = models.CharField(max_length=20, choices=BillingCycle.choices)
    amount = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default='INR')
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['plan', 'billing_cycle'], name='unique_plan_billing_cycle'),
        ]

    def __str__(self):
        return f"{self.plan} {self.billing_cycle}"


class RazorpayPlanMapping(TimeStampedModel):
    class Environment(models.TextChoices):
        TEST = 'test', 'Test'
        LIVE = 'live', 'Live'

    price = models.ForeignKey(PlanPrice, on_delete=models.CASCADE, related_name='razorpay_mappings')
    environment = models.CharField(max_length=10, choices=Environment.choices)
    razorpay_plan_id = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['environment', 'razorpay_plan_id'], name='unique_razorpay_plan_environment'),
        ]


class TenantSubscription(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        TRIAL = 'trial', 'Trial'
        ACTIVE = 'active', 'Active'
        PAYMENT_ISSUE = 'payment_issue', 'Payment Issue'
        GRACE_PERIOD = 'grace_period', 'Grace Period'
        RESTRICTED = 'restricted', 'Restricted'
        SUSPENDED = 'suspended', 'Suspended'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'

    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='tenant_subscriptions')
    razorpay_subscription_id = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.TRIAL, db_index=True)
    billing_cycle = models.CharField(max_length=20, choices=PlanPrice.BillingCycle.choices)
    quantity = models.PositiveIntegerField(default=1)
    start_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    charge_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)


class CustomerAcquisition(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PAYMENT_PENDING = 'payment_pending', 'Payment Pending'
        SUBSCRIPTION_VERIFIED = 'subscription_verified', 'Subscription Verified'
        TENANT_CREATED = 'tenant_created', 'Tenant Created'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='customer_acquisitions')
    plan_price = models.ForeignKey(PlanPrice, on_delete=models.PROTECT, related_name='customer_acquisitions')
    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_acquisition')
    business_name = models.CharField(max_length=255)
    publication_name = models.CharField(max_length=255)
    publication_slug = models.SlugField(max_length=160)
    email = models.EmailField()
    mobile = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.DRAFT, db_index=True)
    provider_subscription_id = models.CharField(max_length=120, blank=True, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['publication_slug'], name='unique_acquisition_publication_slug'),
        ]
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['provider_subscription_id']),
        ]

    def __str__(self):
        return f"{self.publication_name} ({self.status})"


class TenantOnboarding(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        PAYMENT_PENDING = 'payment_pending', 'Payment Pending'
        ONBOARDING = 'onboarding', 'Onboarding'
        SUBMITTED_FOR_REVIEW = 'submitted_for_review', 'Submitted for Review'
        UNDER_REVIEW = 'under_review', 'Under Review'
        CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'
        APPROVED = 'approved', 'Approved'
        READY_TO_PUBLISH = 'ready_to_publish', 'Ready to Publish'
        PUBLISHED = 'published', 'Published'
        SUSPENDED = 'suspended', 'Suspended'
        REJECTED = 'rejected', 'Rejected'

    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='commercial_onboarding')
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.ONBOARDING, db_index=True)
    tagline = models.CharField(max_length=220, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to='tenant-branding/logos/', blank=True)
    header_logo = models.ImageField(upload_to='tenant-branding/header-logos/', blank=True)
    favicon = models.ImageField(upload_to='tenant-branding/favicons/', blank=True)
    primary_color = models.CharField(max_length=20, blank=True)
    secondary_color = models.CharField(max_length=20, blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    youtube_channel_url = models.URLField(blank=True)
    live_tv_url = models.URLField(blank=True)
    site_title = models.CharField(max_length=180, blank=True)
    meta_description = models.TextField(blank=True)
    organization_name = models.CharField(max_length=180, blank=True)
    legal_notes = models.TextField(blank=True)
    reviewer_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tenant} onboarding"


class OnboardingReviewEvent(TimeStampedModel):
    class Action(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted'
        UNDER_REVIEW = 'under_review', 'Under Review'
        CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'
        APPROVED = 'approved', 'Approved'
        PUBLISHED = 'published', 'Published'
        REJECTED = 'rejected', 'Rejected'

    onboarding = models.ForeignKey(TenantOnboarding, on_delete=models.CASCADE, related_name='review_events')
    action = models.CharField(max_length=40, choices=Action.choices)
    notes = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)


class PlanChangeRequest(UUIDModel, TimeStampedModel):
    class ChangeType(models.TextChoices):
        UPGRADE = 'upgrade', 'Upgrade'
        DOWNGRADE = 'downgrade', 'Downgrade'

    class Status(models.TextChoices):
        PENDING_PAYMENT = 'pending_payment', 'Pending Payment'
        VERIFIED = 'verified', 'Verified'
        SCHEDULED = 'scheduled', 'Scheduled'
        APPLIED = 'applied', 'Applied'
        CANCELLED = 'cancelled', 'Cancelled'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='plan_change_requests')
    from_plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='outgoing_plan_changes')
    to_plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='incoming_plan_changes')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True)
    effective_at = models.DateTimeField(null=True, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True, db_index=True)
    notes = models.TextField(blank=True)


class BillingRecord(TimeStampedModel):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='billing_records')
    subscription = models.ForeignKey(TenantSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_records')
    razorpay_payment_id = models.CharField(max_length=120, blank=True, db_index=True)
    razorpay_invoice_id = models.CharField(max_length=120, blank=True, db_index=True)
    amount = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=60, db_index=True)
    payload = JSONTextField(blank=True)


class WebhookEvent(TimeStampedModel):
    environment = models.CharField(max_length=10, choices=RazorpayPlanMapping.Environment.choices)
    provider = models.CharField(max_length=40, default='razorpay')
    event_id = models.CharField(max_length=160)
    event_type = models.CharField(max_length=120, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    payload = JSONTextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['provider', 'environment', 'event_id'], name='unique_provider_webhook_event'),
        ]


class PlatformPolicy(TimeStampedModel):
    class PolicyType(models.TextChoices):
        TERMS = 'terms', 'Terms of Service'
        PRIVACY = 'privacy', 'Privacy Policy'
        REFUND = 'refund', 'Refund/Cancellation Policy'
        BILLING = 'billing', 'Subscription/Billing Policy'
        CONTACT = 'contact', 'Contact'
        GRIEVANCE = 'grievance', 'Support/Grievance Information'

    policy_type = models.CharField(max_length=40, choices=PolicyType.choices, unique=True)
    title = models.CharField(max_length=180)
    content = models.TextField()
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return self.title

# Create your models here.
