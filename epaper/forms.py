from django import forms
from django.core.exceptions import ValidationError

from .models import EPaperEdition


MAX_EPAPER_UPLOAD_MB = 50


class EPaperEditionForm(forms.ModelForm):
    class Meta:
        model = EPaperEdition
        fields = (
            'title',
            'slug',
            'publication_date',
            'edition_name',
            'city',
            'region',
            'pdf_file',
            'cover_image',
            'allow_download',
            'is_featured',
        )

        widgets = {
            'publication_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'pdf_file': forms.ClearableFileInput(attrs={'accept': '.pdf,application/pdf'}),
            'cover_image': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }
        help_texts = {
            'slug': 'A unique URL name, for example daily-edition-06-september.',
            'pdf_file': 'Choose a PDF up to 50 MB.',
            'cover_image': 'Optional. Add a cover to help readers identify this edition.',
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
