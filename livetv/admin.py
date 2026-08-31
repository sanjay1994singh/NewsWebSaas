from django.contrib import admin

from .models import LiveTVChannel


@admin.register(LiveTVChannel)
class LiveTVChannelAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'source_type', 'is_active')
    list_filter = ('source_type', 'is_active')
    search_fields = ('name', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)
