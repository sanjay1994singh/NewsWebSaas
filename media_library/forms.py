from django import forms

from .models import MediaAsset


class MediaAssetForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ['file', 'filename', 'mime_type', 'size', 'media_type', 'alt_text', 'caption']
