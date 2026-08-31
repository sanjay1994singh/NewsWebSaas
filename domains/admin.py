from django.contrib import admin

from .models import TenantDomain


@admin.register(TenantDomain)
class TenantDomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'domain_type', 'is_primary', 'is_verified', 'ssl_status', 'status')
    list_filter = ('domain_type', 'is_primary', 'is_verified', 'ssl_status', 'status')
    search_fields = ('domain', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)
