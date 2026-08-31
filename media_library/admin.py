from django.contrib import admin

from .models import MediaAsset, PhotoGallery, PhotoGalleryItem


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ('filename', 'tenant', 'media_type', 'mime_type', 'size', 'uploaded_by', 'created_at')
    list_filter = ('media_type', 'mime_type')
    search_fields = ('filename', 'alt_text', 'caption', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'uploaded_by')


class PhotoGalleryItemInline(admin.TabularInline):
    model = PhotoGalleryItem
    extra = 0
    autocomplete_fields = ('tenant', 'media')


@admin.register(PhotoGallery)
class PhotoGalleryAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'slug', 'is_published')
    list_filter = ('is_published',)
    search_fields = ('title', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'cover_image')
    inlines = (PhotoGalleryItemInline,)
