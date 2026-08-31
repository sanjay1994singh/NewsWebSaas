from django.contrib import admin

from .models import TenantBranding, ThemeActivation


@admin.register(TenantBranding)
class TenantBrandingAdmin(admin.ModelAdmin):
    list_display = ('publication_name', 'tenant', 'primary_color', 'header_style', 'footer_style')
    search_fields = ('publication_name', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)


@admin.register(ThemeActivation)
class ThemeActivationAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'active_theme', 'draft_theme', 'updated_at')
    list_filter = ('active_theme', 'draft_theme')
    autocomplete_fields = ('tenant',)
