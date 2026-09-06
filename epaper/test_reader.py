from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pymupdf
from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, RequestFactory, override_settings

from tenants.models import Tenant
from .models import EPaperEdition
from .services import mark_epaper_ready
from .views import public_epaper_home, epaper_reader


class OptimizedReaderTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = override_settings(MEDIA_ROOT=self.temp.name, ALLOWED_HOSTS=['testserver'], STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
        settings.enable()
        self.addCleanup(settings.disable)
        user = get_user_model().objects.create_user(username='reader-owner')
        self.tenant = Tenant.objects.create(owner=user, business_name='Daily', publication_name='Daily', slug='daily', email='reader@example.com')

    def edition(self, slug='daily-edition', content=None, **kwargs):
        if content is None:
            with pymupdf.open() as doc:
                for n in range(2):
                    page = doc.new_page(width=595, height=842)
                    page.insert_text((40, 80), f'DAILY NEWS - PAGE {n+1}', fontsize=25)
                content = doc.tobytes()
        return EPaperEdition.objects.create(tenant=self.tenant, title='Daily news', slug=slug, publication_date=date(2026,9,6), pdf_file=SimpleUploadedFile('edition.pdf', content, content_type='application/pdf'), **kwargs)

    def request(self, query=''):
        request = RequestFactory().get('/epaper/' + query)
        request.tenant = self.tenant
        request.user = AnonymousUser()
        return request

    def test_conversion_variants_idempotency_and_publish_preserved(self):
        edition = self.edition(status='published')
        result = mark_epaper_ready(edition)
        self.assertEqual(result.status, 'published')
        self.assertEqual(result.page_count, 2)
        first = result.pages.first()
        for field, limit in [('thumbnail',240),('mobile_image',1000),('image',1800),('zoom_image',3000)]:
            with getattr(first,field).open('rb') as stream:
                img = Image.open(stream)
                self.assertEqual(img.format, 'WEBP')
                self.assertLessEqual(img.width,limit)
        for name in ('image', 'mobile_image', 'zoom_image', 'thumbnail'):
            field = first._meta.get_field(name)
            self.assertEqual(field.max_length, 500)
            self.assertLessEqual(len(getattr(first, name).name), field.max_length)
        original_name = first.image.name
        mark_epaper_ready(edition)
        self.assertEqual(edition.pages.count(),2)
        self.assertEqual(edition.pages.first().image.name,original_name)

    def test_bad_pdf_fails_without_partial_pages(self):
        edition = self.edition(content=b'%PDF-broken')
        with self.assertRaises(Exception):
            mark_epaper_ready(edition)
        edition.refresh_from_db()
        self.assertEqual(edition.status,'failed')
        self.assertEqual(edition.pages.count(),0)

    @patch('epaper.views.can_upload_epaper', return_value=True)
    def test_latest_opens_reader_without_pdf_embed_and_page_link_works(self, access):
        edition = self.edition(status='published')
        mark_epaper_ready(edition)
        response = public_epaper_home(self.request('?page=2'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'id="pageImage"')
        self.assertContains(response,'data-index="1"')
        self.assertNotContains(response,'<iframe')
        self.assertContains(response,'fetchpriority="high"')
        self.assertNotContains(response,'<img loading="lazy"')

    @patch('epaper.views.can_upload_epaper', return_value=True)
    def test_filters_no_match_invalid_date_and_unpublished_hidden(self, access):
        self.edition(city='Delhi', status='published')
        self.edition(slug='draft-only', city='Jaipur', status='draft')
        response = public_epaper_home(self.request('?city=Jaipur'))
        self.assertContains(response,'No edition available')
        response = public_epaper_home(self.request('?date=2026-02-31'))
        self.assertContains(response,'Please choose a valid date.')
        from django.http import Http404
        with self.assertRaises(Http404):
            epaper_reader(self.request(), slug='draft-only')


    def test_storage_failure_cleans_partial_images(self):
        from django.core.files.storage import default_storage
        from pathlib import Path
        edition = self.edition()
        original_save = default_storage.save
        count = 0
        def failing_save(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError('Test storage interruption')
            return original_save(*args, **kwargs)
        with patch.object(default_storage, 'save', side_effect=failing_save):
            with self.assertRaises(OSError):
                mark_epaper_ready(edition)
        self.assertEqual(edition.pages.count(), 0)
        self.assertFalse(list(Path(self.temp.name).rglob('*.webp')))

    def test_worker_prepares_queued_edition(self):
        from django.core.management import call_command
        from io import StringIO
        edition = self.edition(status='processing')
        call_command('prepare_epapers', tenant=self.tenant.slug, stdout=StringIO())
        edition.refresh_from_db()
        self.assertEqual(edition.status, 'ready')
        self.assertEqual(edition.page_count, 2)

    def test_delete_removes_pdf_and_all_page_files_after_commit(self):
        from pathlib import Path
        edition = self.edition()
        mark_epaper_ready(edition)
        pdf_path = edition.pdf_file.path
        images = [getattr(page, name).path for page in edition.pages.all() for name in ('image','mobile_image','zoom_image','thumbnail')]
        with self.captureOnCommitCallbacks(execute=True):
            edition.delete()
        self.assertFalse(Path(pdf_path).exists())
        self.assertTrue(all(not Path(path).exists() for path in images))

    def test_delete_endpoint_owner_scope_and_post_only(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import Http404
        from .views import delete_edition
        edition = self.edition()
        request = RequestFactory().get('/dashboard/epaper/delete/')
        request.user = self.tenant.owner
        self.assertEqual(delete_edition(request, edition.uuid).status_code, 405)
        request = RequestFactory().post('/dashboard/epaper/delete/')
        request.user = get_user_model().objects.create_user(username='other-owner')
        with self.assertRaises(Http404):
            delete_edition(request, edition.uuid)
        self.assertTrue(EPaperEdition.objects.filter(pk=edition.pk).exists())
        request.user = self.tenant.owner
        request.session = {}
        request._messages = FallbackStorage(request)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(delete_edition(request, edition.uuid).status_code, 302)
        self.assertFalse(EPaperEdition.objects.filter(pk=edition.pk).exists())


    def test_active_conversion_cannot_be_deleted(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from .views import delete_edition
        edition = self.edition(status='processing', processing_token='active-worker')
        request = RequestFactory().post('/dashboard/epaper/delete/')
        request.user = self.tenant.owner
        request.session = {}
        request._messages = FallbackStorage(request)
        response = delete_edition(request, edition.uuid)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EPaperEdition.objects.filter(pk=edition.pk).exists())
        from pathlib import Path
        self.assertTrue(Path(edition.pdf_file.path).exists())
