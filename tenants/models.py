from django.conf import settings
from django.db import models

from core.fields import JSONTextField
from core.models import TimeStampedModel, UUIDModel


class Tenant(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        TRIAL = 'trial', 'Trial'
        ACTIVE = 'active', 'Active'
        PAST_DUE = 'past_due', 'Past Due'
        SUSPENDED = 'suspended', 'Suspended'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'

    class OnboardingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETE = 'complete', 'Complete'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_tenants')
    business_name = models.CharField(max_length=255)
    publication_name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=160, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.TRIAL, db_index=True)
    onboarding_status = models.CharField(max_length=32, choices=OnboardingStatus.choices, default=OnboardingStatus.PENDING)
    default_language = models.CharField(max_length=16, default='en')
    timezone = models.CharField(max_length=64, default='UTC')
    country = models.CharField(max_length=80, blank=True)
    email = models.EmailField()
    mobile = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['slug', 'status']),
            models.Index(fields=['owner', 'status']),
        ]

    def __str__(self):
        return self.publication_name


class TenantMembership(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Tenant Owner'
        ADMINISTRATOR = 'administrator', 'Administrator'
        EDITOR = 'editor', 'Editor'
        REPORTER = 'reporter', 'Reporter'
        SEO_MANAGER = 'seo_manager', 'SEO Manager'
        ADVERTISEMENT_MANAGER = 'advertisement_manager', 'Advertisement Manager'

    class Status(models.TextChoices):
        INVITED = 'invited', 'Invited'
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        REMOVED = 'removed', 'Removed'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tenant_memberships')
    role = models.CharField(max_length=40, choices=Role.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.INVITED, db_index=True)
    permissions = JSONTextField(blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'user'], name='unique_tenant_user_membership'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'role', 'status']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"{self.user} - {self.tenant} ({self.role})"


class TenantVisitor(TimeStampedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='visitors')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tenant_visits')
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    mobile = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'user'], name='unique_tenant_visitor_user'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} - {self.tenant}"
