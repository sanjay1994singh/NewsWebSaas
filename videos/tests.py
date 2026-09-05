from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.test import TestCase

from tenants.models import Tenant

from .models import Video
from unittest.mock import patch

from .youtube import _shorts_ids_from_html, _shorts_published_from_html, _shorts_titles_from_html, fetch_youtube_channel_shorts, fetch_youtube_channel_videos


class VideoTests(TestCase):
    def setUp(self):
        cache.clear()
        user = get_user_model().objects.create_user(username='owner')
        self.tenant = Tenant.objects.create(owner=user, business_name='A', publication_name='A', slug='a', email='a@example.com')

    def test_video_rejects_dangerous_url(self):
        video = Video(tenant=self.tenant, title='Bad', slug='bad', source_type=Video.SourceType.YOUTUBE, video_url='javascript:alert(1)')
        with self.assertRaises(ValidationError):
            video.full_clean()

    def test_shorts_parser_extracts_valid_ids_and_titles(self):
        html = (
            '"url":"/shorts/abc123def45","title":{"runs":[{"text":"Mathura latest short"}]}'
            '"publishedTimeText":{"simpleText":"1 day ago"}'
            '"url":"/shorts/xyz987uvw65","accessibilityData":{"label":"\\u092e\\u0925\\u0941\\u0930\\u093e report short"}}'
            '"publishedTimeText":{"simpleText":"3 days ago"}'
        )

        self.assertEqual(_shorts_ids_from_html(html), ['abc123def45', 'xyz987uvw65'])
        titles = _shorts_titles_from_html(html)
        self.assertEqual(titles['abc123def45'], 'Mathura latest short')
        self.assertEqual(titles['xyz987uvw65'], 'मथुरा report short')
        published = _shorts_published_from_html(html)
        self.assertIn('abc123def45', published)
        self.assertIn('xyz987uvw65', published)

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

    def test_video_fetch_merges_feed_and_channel_page_items(self):
        feed = '''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/">
          <entry>
            <yt:videoId>feedvideo12</yt:videoId>
            <title>Today feed video</title>
            <published>2026-09-05T09:00:00+05:30</published>
            <media:group><media:thumbnail url="https://example.com/thumb.jpg" /></media:group>
          </entry>
        </feed>'''
        html = (
            '"url":"/watch?v=feedvideo12","title":{"runs":[{"text":"Duplicate feed video"}]}'
            '"publishedTimeText":{"simpleText":"1 day ago"}'
            '"url":"/watch?v=pagevideo12","title":{"runs":[{"text":"Yesterday page video"}]}'
            '"publishedTimeText":{"simpleText":"1 day ago"}'
        )

        def fake_fetch(url):
            if 'feeds/videos.xml' in url:
                return feed
            return html

        with patch('videos.youtube.extract_youtube_channel_id', return_value='UC12345678901234567890'), patch('videos.youtube._fetch_text', side_effect=fake_fetch):
            videos = fetch_youtube_channel_videos('https://www.youtube.com/@samachar24')

        self.assertEqual([video['id'] for video in videos], ['feedvideo12', 'pagevideo12'])
        self.assertEqual(videos[1]['title'], 'Yesterday page video')
        self.assertTrue(videos[1]['published'])
