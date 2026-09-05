import json
import re
from html import unescape
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.core.cache import cache
from django.utils import timezone


YOUTUBE_FEED_URL = 'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
YOUTUBE_OEMBED_URL = 'https://www.youtube.com/oembed?url={video_url}&format=json'
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


def _channel_tab_url(channel_url, channel_id, tab):
    parsed = urlparse((channel_url or '').strip())
    if parsed.netloc:
        path = parsed.path.strip('/')
        if path:
            first_part = path.split('/')[0]
            if first_part in {'@', 'channel', 'c', 'user'} or path.startswith('@'):
                return f'https://www.youtube.com/{path.split(f"/{tab}", 1)[0].strip("/")}/{tab}'
    return f'https://www.youtube.com/channel/{channel_id}/{tab}'


def _video_ids_from_html(html):
    ids = re.findall(r'"/watch\?v=([0-9A-Za-z_-]{11})"', html)
    ids.extend(re.findall(r'"url":"/watch\?v=([0-9A-Za-z_-]{11})"', html))
    unique_ids = []
    for video_id in ids:
        if video_id not in unique_ids:
            unique_ids.append(video_id)
    return unique_ids


def _titles_from_html(html, video_ids):
    titles = {}
    for video_id in video_ids:
        position = html.find(video_id)
        if position < 0:
            continue
        chunk = html[position:position + 2600]
        patterns = (
            r'"title":\{"runs":\[\{"text":"(?P<title>[^"]+)"',
            r'"simpleText":"(?P<title>[^"]+)"',
            r'"accessibilityData":\{"label":"(?P<title>[^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, chunk)
            title = _clean_youtube_text(match.group('title')) if match else ''
            title_lower = title.lower()
            is_relative_time = bool(re.match(r'^\d+\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago$', title_lower))
            if title and not is_relative_time and not title_lower.startswith(('watch ', 'shorts ', 'play ')):
                titles[video_id] = title
                break
    return titles


def _published_from_html(html, video_ids):
    published = {}
    for video_id in video_ids:
        position = html.find(video_id)
        if position < 0:
            continue
        chunk = html[position:position + 3200]
        patterns = (
            r'"publishedTimeText":\{"simpleText":"(?P<text>[^"]+)"',
            r'"publishedTimeText":\{"runs":\[\{"text":"(?P<text>[^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, chunk)
            published_at = _published_from_relative_text(match.group('text')) if match else ''
            if published_at:
                published[video_id] = published_at
                break
    return published


def _youtube_oembed_title(video_id, is_short=False):
    cache_key = f'youtube-oembed-title:{"short" if is_short else "video"}:{video_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    path = 'shorts' if is_short else 'watch?v='
    video_url = quote(f'https://www.youtube.com/{path}{video_id}', safe='')
    try:
        payload = json.loads(_fetch_text(YOUTUBE_OEMBED_URL.format(video_url=video_url)))
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        cache.set(cache_key, '', 60 * 10)
        return ''

    title = _clean_youtube_text(payload.get('title', ''))
    cache.set(cache_key, title, 60 * 60 * 24)
    return title


def fetch_youtube_channel_videos(channel_url, limit=None):
    channel_id = extract_youtube_channel_id(channel_url)
    if not channel_id:
        return []

    cache_key = f'youtube-feed:{channel_id}:{limit or "all"}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        feed = _fetch_text(YOUTUBE_FEED_URL.format(channel_id=channel_id))
    except (OSError, URLError, ValueError):
        feed = ''

    namespaces = {
        'atom': 'http://www.w3.org/2005/Atom',
        'yt': 'http://www.youtube.com/xml/schemas/2015',
        'media': 'http://search.yahoo.com/mrss/',
    }
    videos = []
    if feed:
        try:
            root = ElementTree.fromstring(feed)
        except ElementTree.ParseError:
            root = None
        if root is not None:
            entries = root.findall('atom:entry', namespaces)
            for entry in entries:
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

    try:
        html = _fetch_text(_channel_tab_url(channel_url, channel_id, 'videos'))
    except (OSError, URLError, ValueError):
        html = ''
    if html:
        existing_ids = {video['id'] for video in videos}
        video_ids = _video_ids_from_html(html)
        titles = _titles_from_html(html, video_ids)
        published_dates = _published_from_html(html, video_ids)
        for video_id in video_ids:
            if video_id in existing_ids:
                continue
            title = titles.get(video_id) or _youtube_oembed_title(video_id) or 'YouTube video'
            videos.append({
                'id': video_id,
                'title': title,
                'description': '',
                'thumbnail': f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'embed_url': f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&rel=0',
                'published': published_dates.get(video_id, ''),
            })
            if limit and len(videos) >= limit:
                break

    cache.set(cache_key, json.loads(json.dumps(videos)), 60 * 30)
    return videos


def _channel_shorts_url(channel_url, channel_id):
    return _channel_tab_url(channel_url, channel_id, 'shorts')


def _clean_youtube_text(value):
    text = unescape(value or '')
    text = text.replace('\\u0026', '&').replace('\\/', '/')
    text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match.group(1), 16)), text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _published_from_relative_text(value):
    text = _clean_youtube_text(value).lower()
    match = re.search(r'(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago', text)
    if not match:
        return ''
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith('minute'):
        delta = timezone.timedelta(minutes=amount)
    elif unit.startswith('hour'):
        delta = timezone.timedelta(hours=amount)
    elif unit.startswith('day'):
        delta = timezone.timedelta(days=amount)
    elif unit.startswith('week'):
        delta = timezone.timedelta(weeks=amount)
    else:
        delta = timezone.timedelta(days=30 * amount)
    return (timezone.now() - delta).isoformat()


def _shorts_published_from_html(html):
    published = {}
    for video_id in _shorts_ids_from_html(html):
        position = html.find(video_id)
        if position < 0:
            continue
        chunk = html[position:position + 2600]
        patterns = (
            r'"publishedTimeText":\{"simpleText":"(?P<text>[^"]+)"',
            r'"publishedTimeText":\{"runs":\[\{"text":"(?P<text>[^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, chunk)
            published_at = _published_from_relative_text(match.group('text')) if match else ''
            if published_at:
                published[video_id] = published_at
                break
    return published


def _shorts_titles_from_html(html):
    titles = {}
    for video_id in _shorts_ids_from_html(html):
        position = html.find(video_id)
        if position < 0:
            continue
        chunk = html[position:position + 2200]
        patterns = (
            r'"title":\{"runs":\[\{"text":"(?P<title>[^"]+)"',
            r'"simpleText":"(?P<title>[^"]+)"',
            r'"accessibilityData":\{"label":"(?P<title>[^"]+)"',
            r'"text":"(?P<title>[^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, chunk)
            title = _clean_youtube_text(match.group('title')) if match else ''
            title_lower = title.lower()
            is_relative_time = bool(re.match(r'^\d+\s+(minute|minutes|hour|hours|day|days|week|weeks)\s+ago$', title_lower))
            if title and not is_relative_time and not title_lower.startswith(('watch ', 'shorts ', 'play ')):
                titles[video_id] = title
                break
    return titles


def _shorts_ids_from_html(html):
    ids = re.findall(r'"/shorts/([0-9A-Za-z_-]{11})"', html)
    ids.extend(re.findall(r'"url":"/shorts/([0-9A-Za-z_-]{11})"', html))
    if not ids:
        ids.extend(re.findall(r'"videoId":"([0-9A-Za-z_-]{11})"', html))
    unique_ids = []
    for video_id in ids:
        if video_id not in unique_ids:
            unique_ids.append(video_id)
    return unique_ids


def fetch_youtube_channel_shorts(channel_url, limit=None):
    channel_id = extract_youtube_channel_id(channel_url)
    if not channel_id:
        return []

    cache_key = f'youtube-shorts:{channel_id}:{limit or "all"}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        html = _fetch_text(_channel_shorts_url(channel_url, channel_id))
    except (OSError, URLError, ValueError):
        cache.set(cache_key, [], 60 * 5)
        return []

    titles = _shorts_titles_from_html(html)
    published_dates = _shorts_published_from_html(html)

    seen = set()
    shorts = []
    for video_id in _shorts_ids_from_html(html):
        if video_id in seen:
            continue
        seen.add(video_id)
        title = titles.get(video_id) or _youtube_oembed_title(video_id, is_short=True) or 'YouTube short'
        shorts.append({
            'id': video_id,
            'title': title,
            'url': f'https://www.youtube.com/shorts/{video_id}',
            'embed_url': f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&rel=0',
            'published': published_dates.get(video_id, ''),
        })
        if limit and len(shorts) >= limit:
            break

    cache.set(cache_key, json.loads(json.dumps(shorts)), 60 * 30)
    return shorts
