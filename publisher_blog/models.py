import re
from html import unescape
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.html import strip_tags
from news.sanitizers import sanitize_html

def word_count(content):
    return len(re.findall(r'\S+', unescape(strip_tags(re.sub(r'<[^>]+>', ' ', content)))))

class Campaign(models.Model):
    name = models.CharField(max_length=120, unique=True, default='Press Nexa 365')
    starts_on = models.DateField()
    days = models.PositiveSmallIntegerField(default=365)
    active = models.BooleanField(default=True)

    def clean(self):
        if not 1 <= self.days <= 365:
            raise ValidationError('Campaign must run for 1–365 days.')

    def __str__(self):
        return self.name

class Post(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Awaiting content'
        READY = 'ready', 'Ready to publish'
        PUBLISHED = 'published', 'Published'
        HOLD = 'hold', 'Editorial hold'

    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, related_name='posts')
    scheduled_at = models.DateTimeField(db_index=True)
    language = models.CharField(max_length=2, choices=[('hi', 'हिंदी'), ('en', 'English')])
    topic = models.CharField(max_length=255)
    slug = models.SlugField(max_length=240, unique=True)
    title = models.CharField(max_length=220, blank=True)
    description = models.CharField(max_length=320, blank=True)
    content = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_at']
        constraints = [models.UniqueConstraint(fields=['campaign', 'scheduled_at'], name='unique_marketing_slot')]

    def clean(self):
        if self.status in {self.Status.READY, self.Status.PUBLISHED}:
            count = word_count(self.content)
            if not 900 <= count <= 1200:
                raise ValidationError({'content': f'Body requires 900–1200 words; found {count}.'})
            if not self.title.strip() or not self.description.strip():
                raise ValidationError('Title and description required.')
        if self.status == self.Status.PUBLISHED and not self.published_at:
            raise ValidationError('Published posts require a publication date.')

    def save(self, *args, **kwargs):
        self.content = sanitize_html(self.content)
        self.full_clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/blog/{self.language}/{self.slug}/'

    def __str__(self):
        return self.title or self.topic

def public_posts():
    now = timezone.now()
    return Post.objects.filter(status=Post.Status.PUBLISHED, published_at__lte=now)

