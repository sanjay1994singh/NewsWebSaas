from django.db import models

from core.models import TenantOwnedModel


class TenantSEOSettings(TenantOwnedModel):
    default_title = models.CharField(max_length=255, blank=True)
    default_meta_description = models.CharField(max_length=320, blank=True)
    default_robots_index = models.BooleanField(default=True)
    default_robots_follow = models.BooleanField(default=True)
    og_image = models.ImageField(upload_to='seo/', blank=True)
    twitter_site = models.CharField(max_length=80, blank=True)
    google_site_verification = models.CharField(max_length=128, blank=True)
    bing_site_verification = models.CharField(max_length=128, blank=True)
    google_analytics_id = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant'], name='unique_seo_settings_per_tenant'),
        ]

    def __str__(self):
        return f"SEO settings for {self.tenant}"

# Create your models here.
