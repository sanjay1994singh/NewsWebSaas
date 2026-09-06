from django import forms
from django.core.validators import RegexValidator
from .models import PlatformEnquiry


class PlatformEnquiryForm(forms.ModelForm):
    consent = forms.BooleanField(label='I agree to be contacted about this enquiry and have read the Privacy Policy.')
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    phone = forms.CharField(required=False, max_length=25, validators=[
        RegexValidator(r'^\+?[0-9 ()-]{7,25}$', 'Enter a valid phone number.')])

    class Meta:
        model = PlatformEnquiry
        fields = ['name', 'email', 'phone', 'message']
        widgets = {'message': forms.Textarea(attrs={'rows': 5, 'maxlength': 5000})}

    def clean_website(self):
        if self.cleaned_data['website']:
            raise forms.ValidationError('Unable to submit this enquiry.')
        return ''
