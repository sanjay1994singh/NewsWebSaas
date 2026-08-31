from django import forms

from .models import TenantBranding, ThemeActivation


class TenantBrandingForm(forms.ModelForm):
    class Meta:
        model = TenantBranding
        fields = [
            'publication_name', 'logo', 'dark_logo', 'mobile_logo', 'favicon',
            'primary_color', 'secondary_color', 'accent_color', 'typography',
            'tagline', 'contact_details', 'copyright_text', 'social_urls',
            'header_style', 'footer_style',
        ]


class ThemeActivationForm(forms.ModelForm):
    class Meta:
        model = ThemeActivation
        fields = ['draft_theme']
