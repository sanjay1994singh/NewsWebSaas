from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from tenants.models import Tenant

from .models import LiveTVChannel


class LiveTVTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='owner')
        self.tenant = Tenant.objects.create(owner=user, business_name='A', publication_name='A', slug='a', email='a@example.com')

    def test_hls_requires_m3u8_url(self):
        channel = LiveTVChannel(tenant=self.tenant, name='Live', slug='live', source_type=LiveTVChannel.SourceType.HLS, stream_url='https://example.com/video.mp4')
        with self.assertRaises(ValidationError):
            channel.full_clean()
