from django import forms

from .models import Page


class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = ['title', 'slug', 'page_type', 'content', 'is_published', 'seo_title', 'meta_description']


class TenantStaticPageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = ['title', 'content', 'seo_title', 'meta_description']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 14}),
            'meta_description': forms.Textarea(attrs={'rows': 3}),
        }
