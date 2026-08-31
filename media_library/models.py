from django.conf import settings
from django.db import models

from core.models import TenantOwnedModel
from core.security import safe_upload_name, validate_upload_file


class MediaAsset(TenantOwnedModel):
    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Image'
        DOCUMENT = 'document', 'Document'
        VIDEO = 'video', 'Video'
        OTHER = 'other', 'Other'

    file = models.FileField(upload_to=safe_upload_name, validators=[validate_upload_file])
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    media_type = models.CharField(max_length=32, choices=MediaType.choices, default=MediaType.OTHER, db_index=True)
    alt_text = models.CharField(max_length=255, blank=True)
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_media_assets')

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'media_type', '-created_at']),
            models.Index(fields=['tenant', 'filename']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return self.filename


class PhotoGallery(TenantOwnedModel):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280)
    description = models.TextField(blank=True)
    cover_image = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='gallery_covers')
    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_gallery_slug_per_tenant')]
        indexes = [models.Index(fields=['tenant', 'is_published'])]

    def clean(self):
        super().clean()
        if self.cover_image_id and self.cover_image.tenant_id != self.tenant_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'cover_image': 'Cover image must belong to the same tenant.'})


class PhotoGalleryItem(TenantOwnedModel):
    gallery = models.ForeignKey(PhotoGallery, on_delete=models.CASCADE, related_name='items')
    media = models.ForeignKey(MediaAsset, on_delete=models.PROTECT, related_name='gallery_items')
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['tenant', 'gallery', 'order'])]
        ordering = ['order', 'id']

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        errors = {}
        if self.gallery_id and self.gallery.tenant_id != self.tenant_id:
            errors['gallery'] = 'Gallery must belong to the same tenant.'
        if self.media_id and self.media.tenant_id != self.tenant_id:
            errors['media'] = 'Media must belong to the same tenant.'
        if errors:
            raise ValidationError(errors)
