from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TenantOwnedModel
from core.security import safe_upload_name, validate_upload_file


class AdPlacement(TenantOwnedModel):
    class Position(models.TextChoices):
        HOMEPAGE_TOP = 'homepage_top', 'Homepage Top'
        HOMEPAGE_MIDDLE = 'homepage_middle', 'Homepage Middle'
        ARTICLE_TOP = 'article_top', 'Article Top'
        ARTICLE_MIDDLE = 'article_middle', 'Article Middle'
        ARTICLE_BOTTOM = 'article_bottom', 'Article Bottom'
        SIDEBAR = 'sidebar', 'Sidebar'
        CATEGORY = 'category', 'Category'
        MOBILE = 'mobile', 'Mobile'

    name = models.CharField(max_length=120)
    position = models.CharField(max_length=40, choices=Position.choices)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'position', 'name'], name='unique_ad_placement_per_tenant')]


class AdCampaign(TenantOwnedModel):
    name = models.CharField(max_length=180)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    impressions = models.PositiveBigIntegerField(default=0)
    clicks = models.PositiveBigIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=['tenant', 'is_active', 'starts_at', 'ends_at'])]

    def clean(self):
        super().clean()
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'End date must be after start date.'})


class AdCreative(TenantOwnedModel):
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name='creatives')
    placement = models.ForeignKey(AdPlacement, on_delete=models.PROTECT, related_name='creatives')
    title = models.CharField(max_length=180)
    image = models.ImageField(upload_to=safe_upload_name, validators=[validate_upload_file])
    destination_url = models.URLField()
    is_active = models.BooleanField(default=True, db_index=True)
    impressions = models.PositiveBigIntegerField(default=0)
    clicks = models.PositiveBigIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=['tenant', 'placement', 'is_active'])]

    def clean(self):
        super().clean()
        errors = {}
        if self.campaign_id and self.campaign.tenant_id != self.tenant_id:
            errors['campaign'] = 'Campaign must belong to the same tenant.'
        if self.placement_id and self.placement.tenant_id != self.tenant_id:
            errors['placement'] = 'Placement must belong to the same tenant.'
        if self.destination_url.lower().startswith('javascript:'):
            errors['destination_url'] = 'Unsafe destination URL.'
        if errors:
            raise ValidationError(errors)
