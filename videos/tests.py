from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from tenants.models import Tenant

from .models import Video


class VideoTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='owner')
        self.tenant = Tenant.objects.create(owner=user, business_name='A', publication_name='A', slug='a', email='a@example.com')

    def test_video_rejects_dangerous_url(self):
        video = Video(tenant=self.tenant, title='Bad', slug='bad', source_type=Video.SourceType.YOUTUBE, video_url='javascript:alert(1)')
        with self.assertRaises(ValidationError):
            video.full_clean()
