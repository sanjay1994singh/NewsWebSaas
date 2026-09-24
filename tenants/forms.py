import re
from django import forms
from core.forms import TrimmedFormMixin
from django.contrib.auth import get_user_model

from seo.models import TenantSEOSettings
from .models import Tenant, TenantAdvertisement, TenantMembership


class TenantSettingsForm(TrimmedFormMixin, forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['business_name', 'publication_name', 'default_language', 'timezone', 'country', 'email', 'mobile', 'customer_gstin', 'article_view_tracking_enabled']
        labels = {
            'customer_gstin': 'GSTIN (optional)',
            'article_view_tracking_enabled': 'Count unique article viewers',
        }
        help_texts = {
            'customer_gstin': 'Used on future GST invoices. Leave blank if you do not have GST registration.',
            'article_view_tracking_enabled': 'When enabled, one viewer is counted only once for the same news article.',
        }

    def clean_customer_gstin(self):
        value = (self.cleaned_data.get('customer_gstin') or '').strip().upper().replace(' ', '')
        if value and not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]', value):
            raise forms.ValidationError('Enter a valid 15-character GSTIN, for example 09ABCDE1234F1Z5.')
        return value


class TenantTrackingForm(TrimmedFormMixin, forms.ModelForm):
    class Meta:
        model = TenantSEOSettings
        fields = [
            'google_site_verification',
            'bing_site_verification',
            'google_analytics_id',
            'google_ads_id',
            'google_ads_conversion_label',
        ]
        labels = {
            'google_site_verification': 'Google site verification code',
            'bing_site_verification': 'Bing site verification code',
            'google_analytics_id': 'Google Analytics measurement ID',
            'google_ads_id': 'Google Ads conversion ID',
            'google_ads_conversion_label': 'Google Ads conversion label',
        }
        help_texts = {
            'google_site_verification': 'Paste only the content value, not the full meta tag.',
            'bing_site_verification': 'Paste only the verification token.',
            'google_analytics_id': 'Example: G-XXXXXXXXXX.',
            'google_ads_id': 'Example: AW-123456789. This loads only on your public domain pages.',
            'google_ads_conversion_label': 'Optional label from Google Ads conversion setup.',
        }

    def _clean_code(self, field_name, pattern, example):
        value = (self.cleaned_data.get(field_name) or '').strip()
        if not value:
            return ''
        if '<' in value or '>' in value:
            raise forms.ValidationError('Paste only the ID/code value, not HTML or script code.')
        if not re.fullmatch(pattern, value):
            raise forms.ValidationError(f'Invalid format. Example: {example}')
        return value

    def clean_google_site_verification(self):
        value = (self.cleaned_data.get('google_site_verification') or '').strip()
        if '<' in value or '>' in value:
            raise forms.ValidationError('Paste only the content value, not the full meta tag.')
        return value

    def clean_bing_site_verification(self):
        value = (self.cleaned_data.get('bing_site_verification') or '').strip()
        if '<' in value or '>' in value:
            raise forms.ValidationError('Paste only the verification token, not the full meta tag.')
        return value

    def clean_google_analytics_id(self):
        return self._clean_code('google_analytics_id', r'G-[A-Z0-9-]{4,32}', 'G-XXXXXXXXXX')

    def clean_google_ads_id(self):
        return self._clean_code('google_ads_id', r'AW-[0-9]{6,20}', 'AW-123456789')

    def clean_google_ads_conversion_label(self):
        value = (self.cleaned_data.get('google_ads_conversion_label') or '').strip()
        if not value:
            return ''
        if '<' in value or '>' in value or not re.fullmatch(r'[A-Za-z0-9_-]{4,80}', value):
            raise forms.ValidationError('Use only the conversion label value from Google Ads.')
        return value

class VisitorRegistrationForm(TrimmedFormMixin, forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    mobile = forms.CharField(max_length=32, required=False)
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('email') and not cleaned.get('mobile'):
            raise forms.ValidationError('Email ya mobile me se ek required hai.')
        if cleaned.get('password') and cleaned.get('confirm_password') and cleaned['password'] != cleaned['confirm_password']:
            self.add_error('confirm_password', 'Passwords do not match.')
        User = get_user_model()
        email = cleaned.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            self.add_error('email', 'This email already has an account.')
        return cleaned


class ReporterCreateForm(TrimmedFormMixin, forms.Form):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    mobile = forms.CharField(max_length=32, required=False)
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(
        choices=[
            (TenantMembership.Role.REPORTER, 'Reporter'),
            (TenantMembership.Role.EDITOR, 'Editor'),
        ],
        initial=TenantMembership.Role.REPORTER,
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email already has an account.')
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') and cleaned.get('confirm_password') and cleaned['password'] != cleaned['confirm_password']:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned

class TenantAdvertisementForm(TrimmedFormMixin, forms.ModelForm):
    class Meta:
        model = TenantAdvertisement
        fields = ['placement', 'title', 'image', 'target_url', 'display_order', 'is_active']
        labels = {
            'placement': 'Ad position',
            'title': 'Ad title / advertiser name (optional)',
            'image': 'Ad image',
            'target_url': 'Click URL (optional)',
            'display_order': 'Display order',
            'is_active': 'Show this ad on website',
        }
        help_texts = {
            'placement': 'Header and after-top-story ads use rectangle 970 x 250 px. Sidebar ads use square 300 x 300 px.',
            'image': 'Upload a clean ad image. Rectangle: 970 x 250 px. Square: 300 x 300 px. The site will auto-fit without stretching.',
            'target_url': 'Optional advertiser URL opened in a new tab.',
            'display_order': 'Lower number shows first when multiple ads use the same position.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['display_order'].initial = self.fields['display_order'].initial or 0
        self.fields['image'].widget.attrs.update({'accept': 'image/*'})