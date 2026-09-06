import uuid

from django.db import models

from core.models import TenantOwnedModel


class PageView(TenantOwnedModel):
    path = models.CharField(max_length=500)
    article = models.ForeignKey('news.NewsArticle', on_delete=models.SET_NULL, null=True, blank=True, related_name='page_views')
    category = models.ForeignKey('categories.Category', on_delete=models.SET_NULL, null=True, blank=True, related_name='page_views')
    unique_visitor_key = models.CharField(max_length=64, blank=True, db_index=True)
    referrer_domain = models.CharField(max_length=255, blank=True, db_index=True)
    device_type = models.CharField(max_length=40, blank=True, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'article', 'unique_visitor_key'],
                condition=models.Q(article__isnull=False, unique_visitor_key__gt=''),
                name='unique_article_view_per_visitor',
            ),
        ]
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


class PlatformVisitor(models.Model):
    """Anonymous browser identity, separate from tenant article analytics."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return str(self.pk)


class PlatformVisit(models.Model):
    visitor = models.ForeignKey(PlatformVisitor, on_delete=models.CASCADE, related_name='visits')
    session_id = models.UUIDField(db_index=True)
    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    path = models.CharField(max_length=500)
    kind = models.CharField(max_length=16, default='page', choices=[('page', 'Page view'), ('login', 'Login'), ('signup', 'Signup')])
    referrer_domain = models.CharField(max_length=255, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    browser = models.CharField(max_length=30, blank=True)
    is_returning = models.BooleanField(default=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-occurred_at', '-pk']
        indexes = [models.Index(fields=['visitor', 'occurred_at'])]


class PlatformEnquiry(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONTACTED = 'contacted', 'Contacted'
        CLOSED = 'closed', 'Closed'

    visitor = models.ForeignKey(PlatformVisitor, null=True, blank=True, on_delete=models.SET_NULL, related_name='enquiries')
    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=25, blank=True)
    message = models.TextField(max_length=5000)
    consent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return self.name
