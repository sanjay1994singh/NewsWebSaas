from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.fields import JSONTextField
from core.models import TenantOwnedModel
from .sanitizers import sanitize_html


class AuthorProfile(TenantOwnedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='author_profiles')
    display_name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180)
    photo = models.ImageField(upload_to='authors/', blank=True)
    bio = models.TextField(blank=True)
    designation = models.CharField(max_length=160, blank=True)
    social_links = JSONTextField(blank=True)
    is_public = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_author_slug_per_tenant'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'is_public']),
            models.Index(fields=['tenant', 'display_name']),
        ]
        ordering = ['display_name']

    def __str__(self):
        return self.display_name


class Tag(TenantOwnedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_tag_slug_per_tenant'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name


class NewsArticle(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        REVIEW = 'review', 'Review'
        SCHEDULED = 'scheduled', 'Scheduled'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    category = models.ForeignKey('categories.Category', on_delete=models.PROTECT, related_name='articles')
    author = models.ForeignKey(AuthorProfile, on_delete=models.PROTECT, related_name='articles')
    reporters = models.ManyToManyField(AuthorProfile, blank=True, related_name='reported_articles')
    tags = models.ManyToManyField(Tag, blank=True, related_name='articles')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280)
    short_description = models.TextField(blank=True)
    content = models.TextField()
    featured_image = models.ImageField(upload_to='articles/', blank=True)
    image_caption = models.CharField(max_length=255, blank=True)
    image_alt = models.CharField(max_length=255, blank=True)
    source_name = models.CharField(max_length=180, blank=True)
    source_url = models.URLField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    is_breaking = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_trending = models.BooleanField(default=False, db_index=True)
    is_editor_pick = models.BooleanField(default=False, db_index=True)
    allow_comments = models.BooleanField(default=True)
    view_count = models.PositiveBigIntegerField(default=0)
    seo_title = models.CharField(max_length=255, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)
    focus_keyword = models.CharField(max_length=160, blank=True)
    canonical_override = models.URLField(blank=True)
    robots_index = models.BooleanField(default=True)
    robots_follow = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_article_slug_per_tenant'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'status', '-published_at']),
            models.Index(fields=['tenant', 'category', 'status']),
            models.Index(fields=['tenant', 'is_breaking', 'status']),
            models.Index(fields=['tenant', 'is_featured', 'status']),
            models.Index(fields=['tenant', 'is_trending', 'status']),
        ]
        ordering = ['-published_at', '-created_at']

    def clean(self):
        super().clean()
        errors = {}
        if self.category_id and self.category.tenant_id != self.tenant_id:
            errors['category'] = 'Category must belong to the same tenant.'
        if self.author_id and self.author.tenant_id != self.tenant_id:
            errors['author'] = 'Author must belong to the same tenant.'
        if self.status == self.Status.SCHEDULED and not self.scheduled_at:
            errors['scheduled_at'] = 'Scheduled articles require a scheduled date.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.content = sanitize_html(self.content)
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def public_publisher_name(self):
        if not self.author_id or not self.author:
            return ''
        name = (self.author.display_name or '').strip()
        if not name:
            return ''
        tenant_names = {
            (self.tenant.publication_name or '').strip().casefold(),
            (self.tenant.business_name or '').strip().casefold(),
            (self.tenant.owner.get_username() or '').strip().casefold() if self.tenant_id and self.tenant.owner_id else '',
        }
        if self.author.slug == 'editor' and name.casefold() in tenant_names:
            return ''
        if self.author.user_id and self.tenant_id and self.author.user_id == self.tenant.owner_id and name.casefold() in tenant_names:
            return ''
        return name

    def __str__(self):
        return self.title


class BreakingNews(TenantOwnedModel):
    article = models.ForeignKey(NewsArticle, on_delete=models.CASCADE, related_name='breaking_items')
    title = models.CharField(max_length=255)
    ticker_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'is_active', 'ticker_order']),
            models.Index(fields=['tenant', 'starts_at', 'ends_at']),
        ]
        ordering = ['ticker_order', '-starts_at']

    def clean(self):
        super().clean()
        if self.article_id and self.article.tenant_id != self.tenant_id:
            raise ValidationError({'article': 'Article must belong to the same tenant.'})
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'End time must be after start time.'})

    @property
    def is_current(self):
        now = timezone.now()
        return self.is_active and self.starts_at <= now and (self.ends_at is None or self.ends_at > now)

    def __str__(self):
        return self.title
