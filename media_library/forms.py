from django import forms
from core.forms import TrimmedFormMixin

from .models import MediaAsset


class MediaAssetForm(TrimmedFormMixin, forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ['file', 'filename', 'mime_type', 'size', 'media_type', 'alt_text', 'caption']
