import os
import tempfile
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from PIL import Image

from .security import redact_log_data, validate_upload_file
from .storage import OptimizedMediaStorage


class SecurityUtilityTests(SimpleTestCase):
    def test_upload_validation_rejects_bad_extension_and_large_file(self):
        bad = SimpleUploadedFile('shell.exe', b'x')
        with self.assertRaises(Exception):
            validate_upload_file(bad)
        large = SimpleUploadedFile('image.jpg', b'x' * (26 * 1024 * 1024))
        with self.assertRaises(Exception):
            validate_upload_file(large)

    def test_log_redaction_masks_sensitive_keys(self):
        redacted = redact_log_data({'password': 'secret', 'name': 'ok', 'razorpay_key_secret': 'hidden'})
        self.assertEqual(redacted['password'], '[REDACTED]')
        self.assertEqual(redacted['razorpay_key_secret'], '[REDACTED]')
        self.assertEqual(redacted['name'], 'ok')


class OptimizedMediaStorageTests(SimpleTestCase):
    def test_large_jpeg_is_resized_and_optimized_before_save(self):
        with tempfile.TemporaryDirectory() as media_root:
            source = BytesIO()
            Image.new('RGB', (1800, 1200), '#0f332c').save(source, format='JPEG', quality=95)
            original = source.getvalue()
            storage = OptimizedMediaStorage(location=media_root)

            with override_settings(MEDIA_IMAGE_MAX_EDGE=800, MEDIA_IMAGE_JPEG_QUALITY=78):
                saved_name = storage.save('uploads/story.jpg', ContentFile(original))

            saved_path = os.path.join(media_root, saved_name)
            self.assertLess(os.path.getsize(saved_path), len(original))
            with Image.open(saved_path) as saved_image:
                self.assertLessEqual(max(saved_image.size), 800)

    def test_non_image_file_is_saved_without_compression(self):
        with tempfile.TemporaryDirectory() as media_root:
            storage = OptimizedMediaStorage(location=media_root)
            content = b'%PDF-1.4 fake-pdf-content'

            saved_name = storage.save('uploads/sample.pdf', ContentFile(content))

            with open(os.path.join(media_root, saved_name), 'rb') as saved_file:
                self.assertEqual(saved_file.read(), content)
