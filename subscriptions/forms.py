from django import forms
from django.utils.text import slugify

from tenants.models import Tenant

from .models import CustomerAcquisition, PlanPrice, TenantOnboarding


class PlanSelectionForm(forms.Form):
    price_id = forms.IntegerField(widget=forms.HiddenInput)

    def clean_price_id(self):
        price_id = self.cleaned_data['price_id']
        try:
            return PlanPrice.objects.select_related('plan').get(pk=price_id, is_active=True, plan__is_active=True)
        except PlanPrice.DoesNotExist as exc:
            raise forms.ValidationError('Selected plan price is not available.') from exc


class CustomerSignupForm(forms.Form):
    business_name = forms.CharField(max_length=255)
    publication_name = forms.CharField(max_length=255)
    email = forms.EmailField()
    mobile = forms.CharField(max_length=32)
    price_id = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'business_name': 'Registered business or publisher name',
            'publication_name': 'News publication name',
            'email': 'owner@example.com',
            'mobile': 'WhatsApp mobile number',
        }
        autocomplete = {
            'business_name': 'organization',
            'publication_name': 'organization-title',
            'email': 'email',
            'mobile': 'tel',
        }
        for name, field in self.fields.items():
            if name in placeholders:
                field.widget.attrs.update({
                    'placeholder': placeholders[name],
                    'autocomplete': autocomplete[name],
                })

    def clean_price_id(self):
        price_id = self.cleaned_data['price_id']
        try:
            return PlanPrice.objects.select_related('plan').get(pk=price_id, is_active=True, plan__is_active=True)
        except PlanPrice.DoesNotExist as exc:
            raise forms.ValidationError('Selected plan price is not available.') from exc

    def clean(self):
        cleaned_data = super().clean()
        publication_name = cleaned_data.get('publication_name')
        if publication_name:
            slug = slugify(publication_name)[:160]
            if Tenant.objects.filter(slug=slug).exists() or CustomerAcquisition.objects.filter(publication_slug=slug).exists():
                self.add_error('publication_name', 'A publication with this name is already reserved.')
            cleaned_data['publication_slug'] = slug
        return cleaned_data


class CustomerWorkspaceForm(forms.Form):
    business_name = forms.CharField(max_length=255)
    publication_name = forms.CharField(max_length=255)
    email = forms.EmailField(required=False)
    mobile = forms.CharField(max_length=32)
    price_id = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.existing_acquisition = None
        super().__init__(*args, **kwargs)
        if user and user.email:
            self.fields['email'].initial = user.email
        placeholders = {
            'business_name': 'Registered business or publisher name',
            'publication_name': 'News publication name',
            'email': 'owner@example.com',
            'mobile': 'WhatsApp mobile number',
        }
        autocomplete = {
            'business_name': 'organization',
            'publication_name': 'organization-title',
            'email': 'email',
            'mobile': 'tel',
        }
        for name, field in self.fields.items():
            if name in placeholders:
                field.widget.attrs.update({
                    'placeholder': placeholders[name],
                    'autocomplete': autocomplete[name],
                })

    def clean_price_id(self):
        price_id = self.cleaned_data['price_id']
        try:
            return PlanPrice.objects.select_related('plan').get(pk=price_id, is_active=True, plan__is_active=True)
        except PlanPrice.DoesNotExist as exc:
            raise forms.ValidationError('Selected plan price is not available.') from exc

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            return email
        if self.user and self.user.email:
            return self.user.email
        return ''

    def clean(self):
        cleaned_data = super().clean()
        publication_name = cleaned_data.get('publication_name')
        if publication_name:
            slug = slugify(publication_name)[:160]
            existing_acquisition = (
                CustomerAcquisition.objects
                .filter(
                    publication_slug=slug,
                    user=self.user,
                    tenant__isnull=True,
                    status=CustomerAcquisition.Status.PAYMENT_PENDING,
                )
                .order_by('-created_at')
                .first()
            )
            if existing_acquisition:
                self.existing_acquisition = existing_acquisition
            elif Tenant.objects.filter(slug=slug).exists() or CustomerAcquisition.objects.filter(publication_slug=slug).exists():
                self.add_error('publication_name', 'A publication with this name is already reserved.')
            cleaned_data['publication_slug'] = slug
        return cleaned_data


class OnboardingForm(forms.ModelForm):
    class Meta:
        model = TenantOnboarding
        fields = (
            'tagline',
            'address',
            'logo',
            'header_logo',
            'favicon',
            'primary_color',
            'secondary_color',
            'facebook_url',
            'instagram_url',
            'twitter_url',
            'youtube_channel_url',
            'live_tv_url',
            'site_title',
            'meta_description',
            'organization_name',
            'legal_notes',
        )


class ReviewActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ('under_review', 'Under Review'),
            ('changes_requested', 'Request Changes'),
            ('approved', 'Approve'),
            ('published', 'Publish'),
            ('rejected', 'Reject'),
        )
    )
    notes = forms.CharField(widget=forms.Textarea, required=False)
