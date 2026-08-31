from django.db import transaction
from django.utils import timezone

from .models import Tenant, TenantMembership


@transaction.atomic
def create_tenant_for_owner(*, owner, business_name, publication_name, slug, email, **extra):
    tenant = Tenant.objects.create(
        owner=owner,
        business_name=business_name,
        publication_name=publication_name,
        slug=slug,
        email=email,
        **extra,
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=owner,
        role=TenantMembership.Role.OWNER,
        status=TenantMembership.Status.ACTIVE,
        joined_at=timezone.now(),
    )
    return tenant
