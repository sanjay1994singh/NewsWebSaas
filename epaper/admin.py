from django.contrib import admin

from .models import EPaperEdition


@admin.register(EPaperEdition)
class EPaperEditionAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'publication_date', 'city', 'status', 'page_count', 'is_featured', 'allow_download')
    list_filter = ('status', 'is_featured', 'allow_download', 'city', 'region')
    search_fields = ('title', 'slug', 'tenant__publication_name', 'city', 'region')
    autocomplete_fields = ('tenant', 'created_by')
