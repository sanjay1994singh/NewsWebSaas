from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q

from subscriptions.forms import disable_autofill
from subscriptions.models import CustomerAcquisition


def _digits(value):
    return ''.join(char for char in str(value or '') if char.isdigit())


class IdentifierAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label='Email, mobile, or username')

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Email, mobile number, or username',
        })
        self.fields['password'].widget.attrs.update({
            'placeholder': 'Password',
        })
        disable_autofill(self.fields)

    def clean_username(self):
        identifier = self.cleaned_data['username'].strip()
        User = get_user_model()
        user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
        if not user:
            digits = _digits(identifier)
            if digits:
                candidates = CustomerAcquisition.objects.select_related('user').filter(mobile__icontains=digits[-10:])
                for acquisition in candidates:
                    if _digits(acquisition.mobile).endswith(digits[-10:]):
                        user = acquisition.user
                        break
        return user.get_username() if user else identifier


class ProfileForm(forms.ModelForm):
    username = forms.CharField(disabled=True, required=False, help_text='Username cannot be changed.')
    full_name = forms.CharField(label='Full name', required=False, max_length=150)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].initial = self.instance.username
        self.fields['full_name'].initial = self.instance.get_full_name()
        self.fields['full_name'].widget.attrs['placeholder'] = 'Example: Geeta Sharma'
        self.fields['email'].widget.attrs['placeholder'] = 'Example: owner@example.com'
        disable_autofill(self.fields)

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data.get('full_name', '').strip()
        parts = full_name.split(None, 1)
        user.first_name = parts[0] if parts else ''
        user.last_name = parts[1] if len(parts) > 1 else ''
        if commit:
            user.save()
        return user

    class Meta:
        model = get_user_model()
        fields = ('username', 'full_name', 'email')
