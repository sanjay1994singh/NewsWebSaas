from django.conf import settings
from django.db import models

from core.fields import JSONTextField
from core.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=120, db_index=True)
    model = models.CharField(max_length=120, db_index=True)
    object_id = models.CharField(max_length=120, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = JSONTextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['model', 'object_id']),
        ]

    def __str__(self):
        return f"{self.action} {self.model}:{self.object_id}"
