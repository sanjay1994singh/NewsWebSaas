from django import forms

from .models import Page


class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = ['title', 'slug', 'page_type', 'content', 'is_published', 'seo_title', 'meta_description']
