from django import forms
from django.utils.text import slugify

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
        widgets = {
            'short_description': forms.Textarea(attrs={'rows': 3}),
            'content': forms.Textarea(attrs={'rows': 12}),
            'meta_description': forms.Textarea(attrs={'rows': 3}),
            'published_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'reporters': forms.CheckboxSelectMultiple,
            'tags': forms.CheckboxSelectMultiple,
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        title = self.cleaned_data.get('title')
        return slugify(slug or title or '')[:280]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False


class BreakingNewsForm(TenantScopedFormMixin, forms.ModelForm):
    tenant_scoped_fields = ('article',)

    class Meta:
        model = BreakingNews
        fields = ['article', 'title', 'ticker_order', 'is_active', 'starts_at', 'ends_at']
