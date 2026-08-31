from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .security import redact_log_data, validate_upload_file


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
