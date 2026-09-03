import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        if tenant is None:
            return self.none()
        return self.filter(tenant=tenant)


class TenantAwareManager(models.Manager):
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant)


class TenantOwnedModel(UUIDModel, TimeStampedModel):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='%(class)ss')

    objects = TenantAwareManager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['tenant']),
        ]

    def assert_tenant_access(self, tenant):
        if tenant is None or self.tenant_id != tenant.id:
            raise PermissionDenied("Object does not belong to the active tenant.")


class TenantScopedFormMixin:
    tenant_scoped_fields = ()

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        for field_name in self.tenant_scoped_fields:
            if field_name in self.fields:
                self.fields[field_name].queryset = self.fields[field_name].queryset.for_tenant(tenant)

    def clean(self):
        cleaned_data = super().clean()
        for field_name in self.tenant_scoped_fields:
            value = cleaned_data.get(field_name)
            if value is None or self.tenant is None:
                continue
            values = value if hasattr(value, '__iter__') and not hasattr(value, 'tenant_id') else [value]
            if any(item.tenant_id != self.tenant.id for item in values):
                self.add_error(field_name, "Selected object is not available for this tenant.")
        return cleaned_data


class TenantScopedViewMixin:
    tenant_kwarg = 'tenant'

    def get_tenant(self):
        return getattr(self.request, 'tenant', None)

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.for_tenant(self.get_tenant())

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        obj.assert_tenant_access(self.get_tenant())
        return obj


def user_can_access_tenant(user, tenant, roles=None):
    if not user.is_authenticated or tenant is None:
        return False
    if getattr(user, "is_super_admin", False) or user.is_superuser:
        return True
    memberships = user.tenant_memberships.filter(tenant=tenant, status='active')
    if roles:
        memberships = memberships.filter(role__in=roles)
    return memberships.exists()
