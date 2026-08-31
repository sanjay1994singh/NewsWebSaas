from django import forms

from core.models import TenantScopedFormMixin

from .models import TenantDomain
from .validators import validate_public_domain


class PrimaryDomainSelectionForm(TenantScopedFormMixin, forms.Form):
    tenant_scoped_fields = ('domain',)
    domain = forms.ModelChoiceField(queryset=TenantDomain.objects.all())


class TenantDomainForm(forms.ModelForm):
    class Meta:
        model = TenantDomain
        fields = ['domain', 'domain_type']

    def clean_domain(self):
        return validate_public_domain(self.cleaned_data['domain'])
