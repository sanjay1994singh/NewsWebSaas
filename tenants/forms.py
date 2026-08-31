from django import forms

from .models import Tenant


class TenantSettingsForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['business_name', 'publication_name', 'default_language', 'timezone', 'country', 'email', 'mobile']
