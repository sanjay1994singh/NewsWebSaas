from django import forms
from django.utils import timezone
from django.utils.text import slugify

from core.models import TenantScopedFormMixin
from categories.models import Category

from .models import AuthorProfile, BreakingNews, NewsArticle


def _safe_slug_from_title(title):
    base = slugify(title or '')[:220]
    if base:
        return base
    return f'post-{timezone.now().strftime("%Y%m%d%H%M%S")}'


class NewsArticleForm(TenantScopedFormMixin, forms.ModelForm):
    tenant_scoped_fields = ('category', 'author', 'reporters', 'tags')
    publisher_name = forms.CharField(
        label='Publisher name on this post',
        max_length=180,
        required=False,
        help_text='This name appears on the news post. Leave blank if you do not want a publisher name shown.',
        widget=forms.TextInput(attrs={'placeholder': 'Example: Ravi Sharma, City Desk, or Editorial Team'}),
    )

    class Meta:
        model = NewsArticle
        fields = [
            'publisher_name',
            'category', 'author', 'reporters', 'tags', 'title', 'content_type', 'slug',
            'short_description', 'content', 'featured_image', 'image_caption',
            'image_alt', 'source_name', 'source_url', 'city', 'state', 'country',
            'latitude', 'longitude', 'status', 'published_at', 'scheduled_at',
            'is_breaking', 'is_featured', 'is_trending', 'is_editor_pick',
            'allow_comments', 'seo_title', 'meta_description', 'focus_keyword',
            'canonical_override', 'robots_index', 'robots_follow',
        ]
        widgets = {
            'slug': forms.HiddenInput(),
            'short_description': forms.Textarea(attrs={'rows': 3}),
            'content': forms.Textarea(attrs={'rows': 12, 'class': 'rich-text-editor'}),
            'meta_description': forms.Textarea(attrs={'rows': 3}),
            'published_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'reporters': forms.CheckboxSelectMultiple,
            'tags': forms.CheckboxSelectMultiple,
        }

    def clean_slug(self):
        title = self.cleaned_data.get('title')
        slug = _safe_slug_from_title(title)
        queryset = NewsArticle.objects.filter(tenant=self.tenant, slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if not queryset.exists():
            return slug
        counter = 2
        while NewsArticle.objects.filter(tenant=self.tenant, slug=f'{slug}-{counter}').exclude(pk=self.instance.pk).exists():
            counter += 1
        return f'{slug}-{counter}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = True
        self.fields['slug'].required = False
        self.fields['content_type'].required = False
        self.fields['category'].required = True
        self.fields['city'].required = True
        self.fields['state'].required = True
        self.fields['content'].required = True
        self.fields['featured_image'].required = not bool(self.instance and self.instance.pk and self.instance.featured_image)
        self.fields['author'].required = False
        self.fields['author'].empty_label = 'Do not show publisher name'
        self.fields['category'].empty_label = 'Select category'
        self.fields['published_at'].required = False
        if not self.is_bound and not self.instance.pk:
            self.fields['published_at'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')
            self.fields['country'].initial = 'India'
        if self.instance and self.instance.pk and self.instance.public_publisher_name:
            self.fields['publisher_name'].initial = self.instance.public_publisher_name

    def clean_publisher_name(self):
        return (self.cleaned_data.get('publisher_name') or '').strip()

    def clean_content_type(self):
        return self.cleaned_data.get('content_type') or NewsArticle.ContentType.NEWS

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('author') or self.instance.author_id:
            return cleaned_data
        author, _ = AuthorProfile.objects.get_or_create(
            tenant=self.tenant,
            slug='editor',
            defaults={'display_name': 'Editorial Desk', 'is_public': False},
        )
        cleaned_data['author'] = author
        self.instance.author = author
        return cleaned_data

    def save(self, commit=True):
        publisher_name = self.cleaned_data.get('publisher_name')
        if publisher_name:
            author_slug = slugify(publisher_name)[:180] or 'publisher'
            author, _ = AuthorProfile.objects.get_or_create(
                tenant=self.tenant,
                slug=author_slug,
                defaults={'display_name': publisher_name, 'is_public': True},
            )
            if author.display_name != publisher_name:
                author.display_name = publisher_name
                author.is_public = True
                author.save(update_fields=['display_name', 'is_public', 'updated_at'])
            self.instance.author = author
        return super().save(commit=commit)


class CategoryForm(TenantScopedFormMixin, forms.ModelForm):
    tenant_scoped_fields = ('parent',)

    class Meta:
        model = Category
        fields = ['name', 'slug', 'description', 'image', 'show_in_menu', 'show_on_homepage', 'is_active']
        widgets = {
            'slug': forms.HiddenInput(),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_slug(self):
        name = self.cleaned_data.get('name')
        slug = slugify(name or '')[:160] or f'category-{timezone.now().strftime("%Y%m%d%H%M%S")}'
        queryset = Category.objects.filter(tenant=self.tenant, slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if not queryset.exists():
            return slug
        counter = 2
        while Category.objects.filter(tenant=self.tenant, slug=f'{slug}-{counter}').exclude(pk=self.instance.pk).exists():
            counter += 1
        return f'{slug}-{counter}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False


class BreakingNewsForm(TenantScopedFormMixin, forms.ModelForm):
    tenant_scoped_fields = ('article',)

    class Meta:
        model = BreakingNews
        fields = ['article', 'title', 'ticker_order', 'is_active', 'starts_at', 'ends_at']
