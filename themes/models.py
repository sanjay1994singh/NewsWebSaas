from django.core.exceptions import ValidationError
from django.db import models

from core.fields import JSONTextField
from core.models import TenantOwnedModel


class TenantBranding(TenantOwnedModel):
    class HeaderStyle(models.TextChoices):
        CLASSIC = 'classic', 'Classic'
        COMPACT = 'compact', 'Compact'
        CENTERED = 'centered', 'Centered'

    class FooterStyle(models.TextChoices):
        SIMPLE = 'simple', 'Simple'
        COLUMNS = 'columns', 'Columns'
        EDITORIAL = 'editorial', 'Editorial'

    publication_name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='branding/', blank=True)
    dark_logo = models.ImageField(upload_to='branding/', blank=True)
    mobile_logo = models.ImageField(upload_to='branding/', blank=True)
    favicon = models.ImageField(upload_to='branding/', blank=True)
    primary_color = models.CharField(max_length=7, default='#1f2937')
    secondary_color = models.CharField(max_length=7, default='#0f766e')
    accent_color = models.CharField(max_length=7, default='#dc2626')
    typography = JSONTextField(blank=True)
    tagline = models.CharField(max_length=255, blank=True)
    contact_details = JSONTextField(blank=True)
    copyright_text = models.CharField(max_length=255, blank=True)
    social_urls = JSONTextField(blank=True)
    header_style = models.CharField(max_length=32, choices=HeaderStyle.choices, default=HeaderStyle.CLASSIC)
    footer_style = models.CharField(max_length=32, choices=FooterStyle.choices, default=FooterStyle.COLUMNS)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant'], name='unique_branding_per_tenant'),
        ]

    def clean(self):
        super().clean()
        for field in ('primary_color', 'secondary_color', 'accent_color'):
            value = getattr(self, field)
            if not value.startswith('#') or len(value) != 7:
                raise ValidationError({field: 'Use a hex color like #123abc.'})

    def __str__(self):
        return self.publication_name


class ThemeActivation(TenantOwnedModel):
    class ThemeKey(models.TextChoices):
        CLASSIC = 'theme_classic', 'Classic'
        MODERN = 'theme_modern', 'Modern'
        TV = 'theme_tv', 'TV'

    active_theme = models.CharField(max_length=40, choices=ThemeKey.choices, default=ThemeKey.CLASSIC)
    draft_theme = models.CharField(max_length=40, choices=ThemeKey.choices, default=ThemeKey.CLASSIC)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant'], name='unique_theme_activation_per_tenant'),
        ]

    def __str__(self):
        return f"{self.tenant}: {self.active_theme}"

# Create your models here.
