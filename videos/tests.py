from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from tenants.models import Tenant

from .models import Video
from unittest.mock import patch

from .youtube import _shorts_ids_from_html, _shorts_titles_from_html, fetch_youtube_channel_shorts


class VideoTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='owner')
        self.tenant = Tenant.objects.create(owner=user, business_name='A', publication_name='A', slug='a', email='a@example.com')

    def test_video_rejects_dangerous_url(self):
        video = Video(tenant=self.tenant, title='Bad', slug='bad', source_type=Video.SourceType.YOUTUBE, video_url='javascript:alert(1)')
        with self.assertRaises(ValidationError):
            video.full_clean()

    def test_shorts_parser_extracts_valid_ids_and_titles(self):
        html = (
            '"url":"/shorts/abc123def45","title":{"runs":[{"text":"Mathura latest short"}]}'
            '"url":"/shorts/xyz987uvw65","accessibilityData":{"label":"Gorakhpur report short"}}'
        )

        self.assertEqual(_shorts_ids_from_html(html), ['abc123def45', 'xyz987uvw65'])
        titles = _shorts_titles_from_html(html)
        self.assertEqual(titles['abc123def45'], 'Mathura latest short')
        self.assertEqual(titles['xyz987uvw65'], 'Gorakhpur report short')

    def test_shorts_fetch_uses_oembed_title_when_page_title_is_missing(self):
        html = '"channelId":"UC12345678901234567890","url":"/shorts/abc123def45"'

        def fake_fetch(url):
            if 'oembed' in url:
                return '{"title": "Actual short title from YouTube"}'
            return html

        with patch('videos.youtube._fetch_text', side_effect=fake_fetch):
            shorts = fetch_youtube_channel_shorts('https://www.youtube.com/@samachar24', limit=1)

        self.assertEqual(shorts[0]['title'], 'Actual short title from YouTube')
        self.assertNotEqual(shorts[0]['title'], 'Latest short')
