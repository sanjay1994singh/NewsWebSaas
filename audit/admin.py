from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model', 'object_id', 'tenant', 'user', 'ip_address', 'created_at')
    list_filter = ('action', 'model', 'created_at')
    search_fields = ('action', 'model', 'object_id', 'tenant__publication_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
