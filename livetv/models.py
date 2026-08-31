from django.core.exceptions import ValidationError
from django.db import models

from core.models import TenantOwnedModel
from videos.models import validate_safe_stream_url


class LiveTVChannel(TenantOwnedModel):
    class SourceType(models.TextChoices):
        YOUTUBE = 'youtube', 'YouTube Live'
        HLS = 'hls', 'HLS'

    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    stream_url = models.URLField(validators=[validate_safe_stream_url])
    poster_image = models.ImageField(upload_to='livetv/', blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_livetv_slug_per_tenant')]
        indexes = [models.Index(fields=['tenant', 'is_active'])]
        ordering = ['name', 'id']

    def clean(self):
        super().clean()
        lowered = (self.stream_url or '').lower()
        if self.source_type == self.SourceType.YOUTUBE and 'youtube.com' not in lowered and 'youtu.be' not in lowered:
            raise ValidationError({'stream_url': 'YouTube Live sources require a YouTube URL.'})
        if self.source_type == self.SourceType.HLS and not lowered.endswith('.m3u8'):
            raise ValidationError({'stream_url': 'HLS sources require an .m3u8 URL.'})

    def __str__(self):
        return self.name
