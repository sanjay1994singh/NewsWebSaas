from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone

from .forms import EPaperEditionForm


class EditionFormTests(SimpleTestCase):
    def make_form(self, **changes):
        data = {'publication_date': '06-09-2026', 'edition_name': 'Delhi', 'city': 'Delhi', 'region': 'North'}
        data.update(changes)
        return EPaperEditionForm(data, {'pdf_file': SimpleUploadedFile('edition.pdf', b'%PDF-1.4\n', content_type='application/pdf')})

    def test_optional_title_and_server_generated_unique_slug(self):
        first = self.make_form(slug='user-supplied', cover_image='ignored')
        second = self.make_form()
        self.assertTrue(first.is_valid(), first.errors)
        self.assertTrue(second.is_valid(), second.errors)
        a, b = first.save(commit=False), second.save(commit=False)
        self.assertEqual(a.title, 'Delhi - 06-09-2026')
        self.assertNotEqual(a.slug, 'user-supplied')
        self.assertNotEqual(a.slug, b.slug)
        self.assertLessEqual(len(a.slug), 180)
        self.assertNotIn('slug', first.fields)
        self.assertNotIn('cover_image', first.fields)
        self.assertFalse(a.cover_image)

    def test_manual_title_and_date_validation(self):
        form = self.make_form(title='Evening news', publication_date='29-02-2024')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save(commit=False).title, 'Evening news')
        self.assertEqual(form.cleaned_data['publication_date'], date(2024, 2, 29))
        for value in ['31-02-2026', '09-13-2026', 'not-a-date']:
            invalid = self.make_form(publication_date=value)
            self.assertFalse(invalid.is_valid())
            self.assertIn('publication_date', invalid.errors)

    def test_today_and_rendered_fields(self):
        form = EPaperEditionForm()
        self.assertEqual(form['publication_date'].value(), timezone.localdate())
        html = render_to_string('epaper/form.html', {'form': form})
        self.assertIn(timezone.localdate().strftime('%d-%m-%Y'), html)
        self.assertNotIn('name="slug"', html)
        self.assertNotIn('name="cover_image"', html)
        for name in form.fields:
            self.assertEqual(html.count('name="' + name + '"'), 1)

    @patch('epaper.forms.EPaperEdition.objects.filter')
    def test_last_saved_values_are_scoped_and_preserve_false(self, query):
        previous = SimpleNamespace(edition_name='Evening', city='Jaipur', region='Rajasthan', allow_download=False, is_featured=True)
        query.return_value.order_by.return_value.first.return_value = previous
        tenant, user = object(), object()
        form = EPaperEditionForm(tenant=tenant, user=user)
        query.assert_called_once_with(tenant=tenant, created_by=user)
        query.return_value.order_by.assert_called_once_with('-created_at', '-pk')
        for name in form.remembered_fields:
            self.assertEqual(form[name].value(), getattr(previous, name))
        self.assertEqual(form['publication_date'].value(), timezone.localdate())

    @patch('epaper.forms.EPaperEdition.objects.filter')
    def test_bound_form_preserves_current_input(self, query):
        form = EPaperEditionForm({'city': 'New city', 'publication_date': '07-09-2026'}, tenant=object(), user=object())
        self.assertFalse(form.is_valid())
        query.assert_not_called()
        self.assertEqual(form['city'].value(), 'New city')
        self.assertFalse(form['allow_download'].value())
        self.assertFalse(form['is_featured'].value())


class EditionUploadRegressionTests(SimpleTestCase):
    def test_only_date_and_pdf_required(self):
        self.assertEqual(
            {name for name, field in EPaperEditionForm().fields.items() if field.required},
            {'publication_date', 'pdf_file'},
        )
        form = EPaperEditionForm(
            {'publication_date': '06-09-2026'},
            {'pdf_file': SimpleUploadedFile('edition.pdf', b'%PDF-1.4\n', content_type='application/pdf')},
        )
        self.assertTrue(form.is_valid(), form.errors)
        edition = form.save(commit=False)
        self.assertEqual(edition.title, 'E-Paper - 06-09-2026')
        self.assertFalse(edition.allow_download)
        self.assertFalse(edition.is_featured)

    def test_ready_edition_dashboard_renders_uuid_publish_link(self):
        from .models import EPaperEdition
        from django.urls import reverse, resolve
        edition = EPaperEdition(id=123, title='Test edition', status='ready')
        url = reverse('epaper:publish_edition', args=[edition.uuid])
        html = render_to_string('epaper/dashboard.html', {'editions': [edition]})
        self.assertIn(url, html)
        self.assertEqual(resolve(url).kwargs['edition_id'], edition.uuid)

    @patch('epaper.views.messages.success')
    @patch('epaper.views.can_upload_epaper', return_value=True)
    @patch('epaper.views.get_object_or_404')
    @patch('epaper.views._owned_tenant')
    def test_publish_looks_up_uuid_with_tenant(self, owned, get_edition, allowed, message):
        from unittest.mock import Mock
        from django.test import RequestFactory
        from .models import EPaperEdition
        from .views import publish_edition
        from uuid import uuid4
        tenant = owned.return_value
        edition = get_edition.return_value
        identifier = uuid4()
        request = RequestFactory().post('/dashboard/epaper/publish/')
        request.user = Mock(is_authenticated=True)
        response = publish_edition(request, identifier)
        get_edition.assert_called_once_with(EPaperEdition, uuid=identifier, tenant=tenant)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(edition.status, EPaperEdition.Status.PUBLISHED)
        edition.save.assert_called_once()
