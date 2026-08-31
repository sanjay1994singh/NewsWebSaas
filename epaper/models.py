from django.conf import settings
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class EPaperEdition(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PROCESSING = 'processing', 'Processing'
        READY = 'ready', 'Ready'
        PUBLISHED = 'published', 'Published'
        FAILED = 'failed', 'Failed'
        ARCHIVED = 'archived', 'Archived'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='epaper_editions')
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180)
    publication_date = models.DateField()
    edition_name = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    pdf_file = models.FileField(upload_to='epaper/pdfs/')
    cover_image = models.ImageField(upload_to='epaper/covers/', blank=True)
    page_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_featured = models.BooleanField(default=False)
    allow_download = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_tenant_epaper_slug'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'status', 'publication_date']),
            models.Index(fields=['tenant', 'city', 'region']),
        ]
        ordering = ('-publication_date', '-created_at')

    def __str__(self):
        return f"{self.tenant} - {self.title}"
