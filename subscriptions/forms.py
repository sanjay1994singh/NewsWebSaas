from django import forms
from django.utils.text import slugify

from tenants.models import Tenant

from .models import CustomerAcquisition, PlanPrice, TenantOnboarding
from .pricing import ALLOWED_BILLING_MONTHS, normalize_billing_months


def disable_autofill(fields):
    for name, field in fields.items():
        field.widget.attrs.update({
            'autocomplete': 'off',
            'autocapitalize': 'off',
            'spellcheck': 'false',
            'data-lpignore': 'true',
            'data-form-type': 'other',
        })
        if not isinstance(field.widget, (forms.FileInput, forms.HiddenInput, forms.Select, forms.Textarea)):
            field.widget.attrs.setdefault('readonly', 'readonly')
            field.widget.attrs.setdefault('onfocus', "this.removeAttribute('readonly')")


class PlanSelectionForm(forms.Form):
    price_id = forms.IntegerField(widget=forms.HiddenInput)

    def clean_price_id(self):
        price_id = self.cleaned_data['price_id']
        try:
            return PlanPrice.objects.select_related('plan').get(pk=price_id, is_active=True, plan__is_active=True)
        except PlanPrice.DoesNotExist as exc:
            raise forms.ValidationError('Selected plan price is not available.') from exc


class CheckoutDurationForm(forms.Form):
    billing_months = forms.ChoiceField(
        label='Subscription duration',
        choices=[(str(months), '1 month' if months == 1 else f'{months} months') for months in ALLOWED_BILLING_MONTHS],
    )

    def clean_billing_months(self):
        return normalize_billing_months(self.cleaned_data.get('billing_months'))


class CustomerSignupForm(forms.Form):
    business_name = forms.CharField(max_length=255, label='Channel name / Paper name')
    publication_name = forms.CharField(max_length=255)
    email = forms.EmailField()
    mobile = forms.CharField(max_length=32)
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput,
        help_text='Use at least 8 characters.',
    )
    confirm_password = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput,
    )
    price_id = forms.IntegerField(widget=forms.HiddenInput)
    billing_months = forms.ChoiceField(
        label='Subscription duration',
        choices=[(str(months), '1 month' if months == 1 else f'{months} months') for months in ALLOWED_BILLING_MONTHS],
        initial='1',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'business_name': 'Channel or newspaper name',
            'publication_name': 'News publication name',
            'email': 'owner@example.com',
            'mobile': 'WhatsApp mobile number',
            'password': 'Create password',
            'confirm_password': 'Confirm password',
        }
        disable_autofill(self.fields)
        for name, field in self.fields.items():
            if name in placeholders:
                field.widget.attrs.update({
                    'placeholder': placeholders[name],
                    'autocomplete': 'off',
                })

    def clean_price_id(self):
        price_id = self.cleaned_data['price_id']
        try:
            return PlanPrice.objects.select_related('plan').get(pk=price_id, is_active=True, plan__is_active=True)
        except PlanPrice.DoesNotExist as exc:
            raise forms.ValidationError('Selected plan price is not available.') from exc

    def clean_billing_months(self):
        return normalize_billing_months(self.cleaned_data.get('billing_months'))

    def clean(self):
        cleaned_data = super().clean()
        business_name = cleaned_data.get('business_name')
        if business_name:
            slug = slugify(business_name)[:160]
            if Tenant.objects.filter(slug=slug).exists() or CustomerAcquisition.objects.filter(publication_slug=slug).exists():
                self.add_error('business_name', 'A channel or paper URL with this name is already reserved.')
            cleaned_data['publication_slug'] = slug
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned_data


class CustomerWorkspaceForm(forms.Form):
    business_name = forms.CharField(max_length=255, label='Channel name / Paper name')
    publication_name = forms.CharField(max_length=255)
    email = forms.EmailField(required=False)
    mobile = forms.CharField(max_length=32)
    price_id = forms.IntegerField(widget=forms.HiddenInput)
    billing_months = forms.ChoiceField(
        label='Subscription duration',
        choices=[(str(months), '1 month' if months == 1 else f'{months} months') for months in ALLOWED_BILLING_MONTHS],
        initial='1',
        required=False,
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.existing_acquisition = None
        super().__init__(*args, **kwargs)
        if user and user.email:
            self.fields['email'].initial = user.email
        placeholders = {
            'business_name': 'Channel or newspaper name',
            'publication_name': 'News publication name',
            'email': 'owner@example.com',
            'mobile': 'WhatsApp mobile number',
        }
        disable_autofill(self.fields)
        for name, field in self.fields.items():
            if name in placeholders:
                field.widget.attrs.update({
                    'placeholder': placeholders[name],
                    'autocomplete': 'off',
                })

    def clean_price_id(self):
        price_id = self.cleaned_data['price_id']
        try:
            return PlanPrice.objects.select_related('plan').get(pk=price_id, is_active=True, plan__is_active=True)
        except PlanPrice.DoesNotExist as exc:
            raise forms.ValidationError('Selected plan price is not available.') from exc

    def clean_billing_months(self):
        return normalize_billing_months(self.cleaned_data.get('billing_months'))

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            return email
        if self.user and self.user.email:
            return self.user.email
        return ''

    def clean(self):
        cleaned_data = super().clean()
        business_name = cleaned_data.get('business_name')
        if business_name:
            slug = slugify(business_name)[:160]
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
                self.add_error('business_name', 'A channel or paper URL with this name is already reserved.')
            cleaned_data['publication_slug'] = slug
        return cleaned_data


class OnboardingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            'tagline': 'Tagline',
            'address': 'Office address',
            'logo': 'Logo',
            'primary_color': 'Primary color',
            'secondary_color': 'Secondary color',
            'site_title': 'Channel name / Paper name',
            'meta_description': 'Website description',
        }
        placeholders = {
            'tagline': 'Example: Fast, reliable digital news for every reader',
            'address': 'Example: 101 Govind Kund Tila, Vrindaban, Mathura, Uttar Pradesh, India',
            'primary_color': 'Example: #0F5331',
            'secondary_color': 'Example: #D71920',
            'site_title': 'Example: The UP Media',
            'meta_description': 'Example: The UP Media covers breaking news, local updates, videos, ePaper, and digital stories.',
        }
        help_texts = {
            'logo': 'Optional. You can upload or change it later from the dashboard.',
            'primary_color': 'Optional. Use a hex color code.',
            'secondary_color': 'Optional. Use a hex color code.',
        }
        disable_autofill(self.fields)
        for field in self.fields.values():
            field.required = False
            field.widget.attrs.pop('required', None)
        for name, label in labels.items():
            self.fields[name].label = label
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs['placeholder'] = placeholder
        tenant = getattr(self.instance, 'tenant', None)
        if tenant and not self.instance.site_title:
            self.fields['site_title'].initial = tenant.business_name
        for name, help_text in help_texts.items():
            self.fields[name].help_text = help_text

    class Meta:
        model = TenantOnboarding
        fields = (
            'tagline',
            'address',
            'logo',
            'primary_color',
            'secondary_color',
            'site_title',
            'meta_description',
        )
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'meta_description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_site_title(self):
        site_title = (self.cleaned_data.get('site_title') or '').strip()
        tenant = getattr(self.instance, 'tenant', None)
        return site_title or (tenant.business_name if tenant else '')


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
