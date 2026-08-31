from django.contrib import admin

from .models import Video


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'source_type', 'status', 'published_at')
    list_filter = ('source_type', 'status')
    search_fields = ('title', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)
