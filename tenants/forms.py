from django import forms
from django.contrib.auth import get_user_model

from .models import Tenant, TenantMembership


class TenantSettingsForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['business_name', 'publication_name', 'default_language', 'timezone', 'country', 'email', 'mobile']


class VisitorRegistrationForm(forms.Form):
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


class ReporterCreateForm(forms.Form):
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
