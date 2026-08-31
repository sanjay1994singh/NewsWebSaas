from django.db import models

from core.models import TenantOwnedModel


class PageView(TenantOwnedModel):
    path = models.CharField(max_length=500)
    article = models.ForeignKey('news.NewsArticle', on_delete=models.SET_NULL, null=True, blank=True, related_name='page_views')
    category = models.ForeignKey('categories.Category', on_delete=models.SET_NULL, null=True, blank=True, related_name='page_views')
    referrer_domain = models.CharField(max_length=255, blank=True, db_index=True)
    device_type = models.CharField(max_length=40, blank=True, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'occurred_at']),
            models.Index(fields=['tenant', 'article', 'occurred_at']),
            models.Index(fields=['tenant', 'category', 'occurred_at']),
        ]


class PlatformSetting(models.Model):
    key = models.CharField(max_length=120, unique=True)
    value = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key

# Create your models here.
