from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import TenantDomain
from .validators import validate_public_domain


def create_domain_for_tenant(*, tenant, domain, domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN):
    normalized = validate_public_domain(domain)
    if TenantDomain.objects.filter(domain=normalized).exists():
        raise ValidationError({'domain': 'This domain is already registered.'})
    return TenantDomain.objects.create(
        tenant=tenant,
        domain=normalized,
        domain_type=domain_type,
        verification_method=TenantDomain.VerificationMethod.DNS_TXT,
        ssl_status=TenantDomain.SSLStatus.PENDING,
        status=TenantDomain.Status.INACTIVE,
    )


def fetch_dns_txt_values(name):
    import dns.resolver

    answers = dns.resolver.resolve(name, 'TXT')
    values = []
    for answer in answers:
        chunks = [part.decode('utf-8') if isinstance(part, bytes) else str(part) for part in answer.strings]
        values.append(''.join(chunks))
    return values


@transaction.atomic
def verify_domain_ownership(domain):
    txt_values = fetch_dns_txt_values(domain.dns_txt_name)
    if domain.expected_txt_value not in txt_values:
        raise ValidationError("DNS TXT verification record was not found.")
    domain.is_verified = True
    domain.verified_at = timezone.now()
    domain.status = TenantDomain.Status.ACTIVE
    domain.ssl_status = TenantDomain.SSLStatus.PENDING
    domain.save(update_fields=['is_verified', 'verified_at', 'status', 'ssl_status', 'updated_at'])
    return domain


@transaction.atomic
def set_primary_domain(*, tenant, domain_id):
    try:
        domain = TenantDomain.objects.for_tenant(tenant).get(pk=domain_id)
    except TenantDomain.DoesNotExist as exc:
        raise PermissionDenied("Domain does not belong to the active tenant.") from exc
    if not domain.is_verified or domain.status != TenantDomain.Status.ACTIVE:
        raise ValidationError("Only verified active domains can be primary.")
    TenantDomain.objects.for_tenant(tenant).exclude(pk=domain.pk).update(is_primary=False)
    domain.is_primary = True
    domain.save(update_fields=['is_primary', 'updated_at'])
    return domain


def enqueue_ssl_provisioning(domain):
    domain.ssl_status = TenantDomain.SSLStatus.PROVISIONING
    domain.ssl_last_checked_at = timezone.now()
    domain.ssl_provisioning_error = ''
    domain.save(update_fields=['ssl_status', 'ssl_last_checked_at', 'ssl_provisioning_error', 'updated_at'])
    return domain
