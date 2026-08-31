from django.core.exceptions import ValidationError
from django.db import models

from core.fields import JSONTextField
from core.models import TenantOwnedModel
from news.sanitizers import sanitize_html


class Page(TenantOwnedModel):
    class PageType(models.TextChoices):
        ABOUT = 'about', 'About Us'
        CONTACT = 'contact', 'Contact Us'
        PRIVACY = 'privacy', 'Privacy Policy'
        TERMS = 'terms', 'Terms'
        DISCLAIMER = 'disclaimer', 'Disclaimer'
        EDITORIAL_POLICY = 'editorial_policy', 'Editorial Policy'
        CORRECTIONS_POLICY = 'corrections_policy', 'Corrections Policy'
        ETHICS_POLICY = 'ethics_policy', 'Ethics Policy'
        ADVERTISE = 'advertise', 'Advertise With Us'
        CUSTOM = 'custom', 'Custom Page'

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280)
    page_type = models.CharField(max_length=40, choices=PageType.choices, default=PageType.CUSTOM, db_index=True)
    content = models.TextField()
    is_published = models.BooleanField(default=False, db_index=True)
    seo_title = models.CharField(max_length=255, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'slug'], name='unique_page_slug_per_tenant'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'page_type']),
            models.Index(fields=['tenant', 'is_published']),
        ]
        ordering = ['title']

    def save(self, *args, **kwargs):
        self.content = sanitize_html(self.content)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class HomepageLayout(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    name = models.CharField(max_length=120, default='Homepage')
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT, db_index=True)
    theme_key = models.CharField(max_length=40, default='theme_classic')
    published_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='draft_restores')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'status'], name='unique_homepage_layout_status_per_tenant'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'status']),
        ]

    def __str__(self):
        return f"{self.tenant} {self.status} homepage"


class HomepageBlock(TenantOwnedModel):
    class BlockType(models.TextChoices):
        BREAKING_NEWS = 'breaking_news', 'Breaking News Ticker'
        HERO_NEWS = 'hero_news', 'Hero News'
        LATEST_NEWS = 'latest_news', 'Latest News'
        CATEGORY_NEWS = 'category_news', 'Category News'
        NEWS_GRID = 'news_grid', 'News Grid'
        NEWS_LIST = 'news_list', 'News List'
        TRENDING = 'trending', 'Trending'
        EDITOR_PICKS = 'editor_picks', 'Editor Picks'
        VIDEOS = 'videos', 'Videos'
        LIVE_TV = 'live_tv', 'Live TV'
        PHOTO_GALLERY = 'photo_gallery', 'Photo Gallery'
        ADVERTISEMENT = 'advertisement', 'Advertisement'
        CUSTOM_CONTENT = 'custom_content', 'Custom Content'

    layout = models.ForeignKey(HomepageLayout, on_delete=models.CASCADE, related_name='blocks')
    block_type = models.CharField(max_length=40, choices=BlockType.choices)
    heading = models.CharField(max_length=180, blank=True)
    category = models.ForeignKey('categories.Category', on_delete=models.PROTECT, null=True, blank=True, related_name='homepage_blocks')
    order = models.PositiveIntegerField(default=0, db_index=True)
    is_enabled = models.BooleanField(default=True, db_index=True)
    article_count = models.PositiveIntegerField(default=6)
    layout_variant = models.CharField(max_length=60, default='standard')
    show_image = models.BooleanField(default=True)
    show_description = models.BooleanField(default=True)
    desktop_columns = models.PositiveIntegerField(default=3)
    settings = JSONTextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'layout', 'order']),
            models.Index(fields=['tenant', 'block_type', 'is_enabled']),
        ]
        ordering = ['order', 'id']

    def clean(self):
        super().clean()
        errors = {}
        if self.layout_id and self.layout.tenant_id != self.tenant_id:
            errors['layout'] = 'Layout must belong to the same tenant.'
        if self.category_id and self.category.tenant_id != self.tenant_id:
            errors['category'] = 'Category must belong to the same tenant.'
        if self.block_type == self.BlockType.CATEGORY_NEWS and not self.category_id:
            errors['category'] = 'Category news blocks require a category.'
        if self.article_count < 1 or self.article_count > 50:
            errors['article_count'] = 'Article count must be between 1 and 50.'
        if self.desktop_columns < 1 or self.desktop_columns > 6:
            errors['desktop_columns'] = 'Desktop columns must be between 1 and 6.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        custom_content = (self.settings or {}).get('content')
        if self.block_type == self.BlockType.CUSTOM_CONTENT and custom_content:
            self.settings = {**self.settings, 'content': sanitize_html(custom_content)}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.heading or self.get_block_type_display()


class Menu(models.Model):
    class Location(models.TextChoices):
        HEADER = 'header', 'Header'
        FOOTER = 'footer', 'Footer'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='menus')
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=32, choices=Location.choices, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'location'], name='unique_menu_location_per_tenant'),
        ]

    def __str__(self):
        return self.name


class MenuItem(TenantOwnedModel):
    class LinkType(models.TextChoices):
        HOME = 'home', 'Home'
        CATEGORY = 'category', 'Category'
        PAGE = 'page', 'Page'
        VIDEOS = 'videos', 'Videos'
        LIVE_TV = 'live_tv', 'Live TV'
        EXTERNAL = 'external', 'External Link'

    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name='items')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    label = models.CharField(max_length=120)
    link_type = models.CharField(max_length=32, choices=LinkType.choices)
    category = models.ForeignKey('categories.Category', on_delete=models.PROTECT, null=True, blank=True, related_name='menu_items')
    page = models.ForeignKey(Page, on_delete=models.PROTECT, null=True, blank=True, related_name='menu_items')
    external_url = models.URLField(blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    is_enabled = models.BooleanField(default=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'menu', 'parent', 'order']),
        ]
        ordering = ['order', 'id']

    def clean(self):
        super().clean()
        errors = {}
        if self.menu_id and self.menu.tenant_id != self.tenant_id:
            errors['menu'] = 'Menu must belong to the same tenant.'
        if self.parent_id and self.parent.tenant_id != self.tenant_id:
            errors['parent'] = 'Parent item must belong to the same tenant.'
        if self.category_id and self.category.tenant_id != self.tenant_id:
            errors['category'] = 'Category must belong to the same tenant.'
        if self.page_id and self.page.tenant_id != self.tenant_id:
            errors['page'] = 'Page must belong to the same tenant.'
        if self.link_type == self.LinkType.CATEGORY and not self.category_id:
            errors['category'] = 'Category link requires a category.'
        if self.link_type == self.LinkType.PAGE and not self.page_id:
            errors['page'] = 'Page link requires a page.'
        if self.link_type == self.LinkType.EXTERNAL and not self.external_url:
            errors['external_url'] = 'External link requires a URL.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.label


class FooterSection(TenantOwnedModel):
    title = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0, db_index=True)
    is_enabled = models.BooleanField(default=True, db_index=True)
    settings = JSONTextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'order']),
            models.Index(fields=['tenant', 'is_enabled']),
        ]
        ordering = ['order', 'id']

    def __str__(self):
        return self.title
