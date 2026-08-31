from django import forms

from core.models import TenantScopedFormMixin

from .models import BreakingNews, NewsArticle


class NewsArticleForm(TenantScopedFormMixin, forms.ModelForm):
    tenant_scoped_fields = ('category', 'author', 'reporters', 'tags')

    class Meta:
        model = NewsArticle
        fields = [
            'category', 'author', 'reporters', 'tags', 'title', 'slug',
            'short_description', 'content', 'featured_image', 'image_caption',
            'image_alt', 'source_name', 'source_url', 'city', 'state', 'country',
            'latitude', 'longitude', 'status', 'published_at', 'scheduled_at',
            'is_breaking', 'is_featured', 'is_trending', 'is_editor_pick',
            'allow_comments', 'seo_title', 'meta_description', 'focus_keyword',
            'canonical_override', 'robots_index', 'robots_follow',
        ]


class BreakingNewsForm(TenantScopedFormMixin, forms.ModelForm):
    tenant_scoped_fields = ('article',)

    class Meta:
        model = BreakingNews
        fields = ['article', 'title', 'ticker_order', 'is_active', 'starts_at', 'ends_at']
