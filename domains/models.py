import secrets

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TenantAwareManager, TimeStampedModel, UUIDModel


class TenantDomain(UUIDModel, TimeStampedModel):
    class DomainType(models.TextChoices):
        PLATFORM_SUBDOMAIN = 'platform_subdomain', 'Platform Subdomain'
        CUSTOM_DOMAIN = 'custom_domain', 'Custom Domain'

    class VerificationMethod(models.TextChoices):
        DNS_TXT = 'dns_txt', 'DNS TXT'
        FILE = 'file', 'File'
        CNAME = 'cname', 'CNAME'

    class SSLStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROVISIONING = 'provisioning', 'Provisioning'
        ACTIVE = 'active', 'Active'
        FAILED = 'failed', 'Failed'
        RENEWING = 'renewing', 'Renewing'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        BLOCKED = 'blocked', 'Blocked'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='domains')
    domain = models.CharField(max_length=255, unique=True)
    domain_type = models.CharField(max_length=32, choices=DomainType.choices)
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False, db_index=True)
    verification_token = models.CharField(max_length=96, default=secrets.token_urlsafe)
    verification_method = models.CharField(max_length=32, choices=VerificationMethod.choices, default=VerificationMethod.DNS_TXT)
    ssl_status = models.CharField(max_length=32, choices=SSLStatus.choices, default=SSLStatus.PENDING)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    ssl_provisioning_error = models.TextField(blank=True)
    ssl_last_checked_at = models.DateTimeField(null=True, blank=True)

    objects = TenantAwareManager()

    class Meta:
        indexes = [
            models.Index(fields=['domain', 'status']),
            models.Index(fields=['tenant', 'domain_type']),
        ]

    def save(self, *args, **kwargs):
        from .validators import validate_public_domain

        self.domain = validate_public_domain(self.domain)
        if self.is_verified and self.verified_at is None:
            self.verified_at = timezone.now()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.domain = normalize_hostname(self.domain)
        if self.is_primary and self.tenant_id:
            primary_exists = TenantDomain.objects.filter(tenant=self.tenant, is_primary=True).exclude(pk=self.pk).exists()
            if primary_exists:
                raise ValidationError({'is_primary': 'Only one primary domain is allowed per tenant.'})

    @property
    def dns_txt_name(self):
        return f"_infosaas-verify.{self.domain}"

    @property
    def expected_txt_value(self):
        return f"infosaas-domain-verification={self.verification_token}"

    def __str__(self):
        return self.domain


def normalize_hostname(host):
    host = (host or "").strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host
