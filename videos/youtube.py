import json
import re
from html import unescape
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.core.cache import cache


YOUTUBE_FEED_URL = 'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
YOUTUBE_TIMEOUT = 6
YOUTUBE_USER_AGENT = 'PressNexaBot/1.0'


def _fetch_text(url):
    request = Request(url, headers={'User-Agent': YOUTUBE_USER_AGENT})
    with urlopen(request, timeout=YOUTUBE_TIMEOUT) as response:
        return response.read().decode('utf-8', errors='replace')


def extract_youtube_channel_id(channel_url):
    parsed = urlparse((channel_url or '').strip())
    if not parsed.netloc:
        return ''
    host = parsed.netloc.lower().replace('www.', '')
    if host not in {'youtube.com', 'm.youtube.com', 'youtu.be'}:
        return ''

    path = parsed.path.strip('/')
    if path.startswith('channel/'):
        return path.split('/', 1)[1].split('/')[0]

    query_channel_id = parse_qs(parsed.query).get('channel_id', [''])[0]
    if query_channel_id.startswith('UC'):
        return query_channel_id

    cache_key = f'youtube-channel-id:{channel_url}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        html = _fetch_text(channel_url)
    except (OSError, URLError, ValueError):
        cache.set(cache_key, '', 60 * 10)
        return ''

    patterns = (
        r'"channelId"\s*:\s*"(?P<id>UC[0-9A-Za-z_-]{20,})"',
        r'<meta itemprop="channelId" content="(?P<id>UC[0-9A-Za-z_-]{20,})"',
        r'https://www\.youtube\.com/channel/(?P<id>UC[0-9A-Za-z_-]{20,})',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            channel_id = match.group('id')
            cache.set(cache_key, channel_id, 60 * 60 * 24)
            return channel_id

    cache.set(cache_key, '', 60 * 10)
    return ''


def _entry_text(entry, name, namespaces):
    found = entry.find(name, namespaces)
    return unescape(found.text or '').strip() if found is not None else ''


def fetch_youtube_channel_videos(channel_url, limit=12):
    channel_id = extract_youtube_channel_id(channel_url)
    if not channel_id:
        return []

    cache_key = f'youtube-feed:{channel_id}:{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        feed = _fetch_text(YOUTUBE_FEED_URL.format(channel_id=channel_id))
    except (OSError, URLError, ValueError):
        cache.set(cache_key, [], 60 * 5)
        return []

    namespaces = {
        'atom': 'http://www.w3.org/2005/Atom',
        'yt': 'http://www.youtube.com/xml/schemas/2015',
        'media': 'http://search.yahoo.com/mrss/',
    }
    videos = []
    try:
        root = ElementTree.fromstring(feed)
    except ElementTree.ParseError:
        cache.set(cache_key, [], 60 * 5)
        return []

    for entry in root.findall('atom:entry', namespaces)[:limit]:
        video_id = _entry_text(entry, 'yt:videoId', namespaces)
        title = _entry_text(entry, 'atom:title', namespaces)
        published = _entry_text(entry, 'atom:published', namespaces)
        media_group = entry.find('media:group', namespaces)
        description = ''
        thumbnail = ''
        if media_group is not None:
            description = _entry_text(media_group, 'media:description', namespaces)
            thumb = media_group.find('media:thumbnail', namespaces)
            if thumb is not None:
                thumbnail = thumb.attrib.get('url', '')
        if video_id and title:
            videos.append({
                'id': video_id,
                'title': title,
                'description': description,
                'thumbnail': thumbnail or f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'embed_url': f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&rel=0',
                'published': published,
            })

    cache.set(cache_key, json.loads(json.dumps(videos)), 60 * 30)
    return videos


def _channel_shorts_url(channel_url, channel_id):
    parsed = urlparse((channel_url or '').strip())
    if parsed.netloc:
        path = parsed.path.strip('/')
        if path:
            first_part = path.split('/')[0]
            if first_part in {'@', 'channel', 'c', 'user'} or path.startswith('@'):
                return f'https://www.youtube.com/{path.split("/shorts", 1)[0].strip("/")}/shorts'
    return f'https://www.youtube.com/channel/{channel_id}/shorts'


def fetch_youtube_channel_shorts(channel_url, limit=12):
    channel_id = extract_youtube_channel_id(channel_url)
    if not channel_id:
        return []

    cache_key = f'youtube-shorts:{channel_id}:{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        html = _fetch_text(_channel_shorts_url(channel_url, channel_id))
    except (OSError, URLError, ValueError):
        cache.set(cache_key, [], 60 * 5)
        return []

    titles = {}
    for match in re.finditer(r'"videoId":"(?P<id>[0-9A-Za-z_-]{11})".{0,900}?"title":\{"runs":\[\{"text":"(?P<title>[^"]+)"', html):
        titles.setdefault(match.group('id'), unescape(match.group('title')))
    for match in re.finditer(r'"videoId":"(?P<id>[0-9A-Za-z_-]{11})".{0,900}?"simpleText":"(?P<title>[^"]+)"', html):
        titles.setdefault(match.group('id'), unescape(match.group('title')))

    seen = set()
    shorts = []
    for video_id in re.findall(r'"videoId":"([0-9A-Za-z_-]{11})"', html):
        if video_id in seen:
            continue
        seen.add(video_id)
        shorts.append({
            'id': video_id,
            'title': titles.get(video_id) or 'YouTube Short',
            'url': f'https://www.youtube.com/shorts/{video_id}',
            'embed_url': f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&rel=0',
        })
        if len(shorts) >= limit:
            break

    cache.set(cache_key, json.loads(json.dumps(shorts)), 60 * 30)
    return shorts
