from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify

from .models import EPaperEdition


MAX_EPAPER_UPLOAD_MB = 50


class EPaperEditionForm(forms.ModelForm):
    title = forms.CharField(max_length=180, required=False, help_text='Optional. Leave blank to use the edition name and date.')
    publication_date = forms.DateField(
        initial=timezone.localdate,
        input_formats=['%d-%m-%Y'],
        widget=forms.DateInput(format='%d-%m-%Y', attrs={
            'inputmode': 'numeric', 'placeholder': 'DD-MM-YYYY',
            'maxlength': '10', 'pattern': '[0-9]{2}-[0-9]{2}-[0-9]{4}',
            'data-date-mask': '', 'autocomplete': 'off',
        }),
        help_text='Enter digits as DD-MM-YYYY. Dashes are added automatically.',
    )
    remembered_fields = ('edition_name', 'city', 'region', 'allow_download', 'is_featured')

    def __init__(self, *args, tenant=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.instance.pk and tenant is not None and user is not None:
            previous = EPaperEdition.objects.filter(tenant=tenant, created_by=user).order_by('-created_at', '-pk').first()
            if previous is not None:
                for name in self.remembered_fields:
                    self.initial[name] = getattr(previous, name)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('title') and cleaned.get('publication_date'):
            name = cleaned.get('edition_name') or 'E-Paper'
            cleaned['title'] = f"{name} - {cleaned['publication_date']:%d-%m-%Y}"[:180]
        return cleaned

    def save(self, commit=True):
        edition = super().save(commit=False)
        if not edition.slug:
            # The immutable UUID keeps repeated titles/dates unique, including concurrent uploads.
            base = slugify(edition.title)[:140] or 'epaper'
            edition.slug = f'{base}-{edition.uuid.hex}'
        if commit:
            edition.save()
            self.save_m2m()
        return edition

    class Meta:
        model = EPaperEdition
        fields = (
            'title',
            'publication_date',
            'edition_name',
            'city',
            'region',
            'pdf_file',
            'allow_download',
            'is_featured',
        )

        widgets = {
            'pdf_file': forms.ClearableFileInput(attrs={'accept': '.pdf,application/pdf'}),
        }
        help_texts = {
            'pdf_file': 'Choose a PDF up to 50 MB.',
            'allow_download': 'Let readers download the edition PDF.',
            'is_featured': 'Highlight this edition for your readers.',
        }

    def clean_pdf_file(self):
        pdf_file = self.cleaned_data['pdf_file']
        name = pdf_file.name.lower()
        content_type = getattr(pdf_file, 'content_type', '')
        if not name.endswith('.pdf'):
            raise ValidationError('Only PDF files are allowed.')
        if content_type and content_type not in {'application/pdf', 'application/x-pdf'}:
            raise ValidationError('Uploaded file must be a PDF.')
        if pdf_file.size > MAX_EPAPER_UPLOAD_MB * 1024 * 1024:
            raise ValidationError(f'PDF must be {MAX_EPAPER_UPLOAD_MB} MB or smaller.')
        head = pdf_file.read(5)
        pdf_file.seek(0)
        if head != b'%PDF-':
            raise ValidationError('Uploaded file is not a valid PDF.')
        return pdf_file
