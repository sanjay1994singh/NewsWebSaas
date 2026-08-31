from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TenantOwnedModel
from core.security import safe_upload_name, validate_upload_file


def validate_safe_stream_url(value):
    if not value:
        return
    allowed = ('https://www.youtube.com/', 'https://youtube.com/', 'https://youtu.be/', 'https://player.vimeo.com/', 'https://', 'http://')
    if not value.startswith(allowed):
        raise ValidationError('Unsupported or unsafe video URL.')
    if value.lower().startswith('javascript:') or '<script' in value.lower():
        raise ValidationError('Unsafe video URL.')


class Video(TenantOwnedModel):
    class SourceType(models.TextChoices):
        YOUTUBE = 'youtube', 'YouTube'
        HLS = 'hls', 'HLS'
        FILE = 'file', 'File'
        VIMEO = 'vimeo', 'Vimeo'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to=safe_upload_name, blank=True, validators=[validate_upload_file])
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    video_url = models.URLField(blank=True, validators=[validate_safe_stream_url])
    video_file = models.FileField(upload_to=safe_upload_name, blank=True, validators=[validate_upload_file])
    duration = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    seo_title = models.CharField(max_length=255, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_video_slug_per_tenant')]
        indexes = [models.Index(fields=['tenant', 'status', '-published_at'])]
        ordering = ['-published_at', '-created_at']

    def clean(self):
        super().clean()
        if self.source_type == self.SourceType.FILE and not self.video_file:
            raise ValidationError({'video_file': 'File videos require an uploaded file.'})
        if self.source_type != self.SourceType.FILE and not self.video_url:
            raise ValidationError({'video_url': 'Embedded videos require a URL.'})

    def save(self, *args, **kwargs):
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
