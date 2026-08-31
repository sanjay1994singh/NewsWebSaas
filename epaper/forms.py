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
