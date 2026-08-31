from django.db import models

from core.models import TenantOwnedModel


class Category(TenantOwnedModel):
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True)
    icon = models.CharField(max_length=80, blank=True)
    menu_order = models.PositiveIntegerField(default=0, db_index=True)
    homepage_order = models.PositiveIntegerField(default=0, db_index=True)
    show_in_menu = models.BooleanField(default=True)
    show_on_homepage = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    seo_title = models.CharField(max_length=255, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_category_slug_per_tenant'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'parent', 'menu_order']),
            models.Index(fields=['tenant', 'is_active', 'show_in_menu']),
            models.Index(fields=['tenant', 'is_active', 'show_on_homepage']),
        ]
        ordering = ['menu_order', 'name']

    def clean(self):
        super().clean()
        if self.parent_id and self.parent.tenant_id != self.tenant_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'parent': 'Parent category must belong to the same tenant.'})

    def __str__(self):
        return self.name
