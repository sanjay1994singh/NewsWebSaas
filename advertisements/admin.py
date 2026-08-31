from django.contrib import admin

from .models import AdCampaign, AdCreative, AdPlacement


@admin.register(AdPlacement)
class AdPlacementAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'position', 'is_active')
    list_filter = ('position', 'is_active')
    search_fields = ('name', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'is_active', 'starts_at', 'ends_at', 'impressions', 'clicks')
    list_filter = ('is_active',)
    search_fields = ('name', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)


@admin.register(AdCreative)
class AdCreativeAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'campaign', 'placement', 'is_active', 'impressions', 'clicks')
    list_filter = ('is_active',)
    search_fields = ('title', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'campaign', 'placement')
