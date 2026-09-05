import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime


YOUTUBE_FEED_URL = 'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
YOUTUBE_OEMBED_URL = 'https://www.youtube.com/oembed?url={video_url}&format=json'
YOUTUBE_BROWSE_URL = 'https://www.youtube.com/youtubei/v1/browse?key={api_key}'
YOUTUBE_TIMEOUT = 6
YOUTUBE_USER_AGENT = 'PressNexaBot/1.0'
YOUTUBE_CACHE_VERSION = 'v9'


def _fetch_text(url):
    request = Request(url, headers={'User-Agent': YOUTUBE_USER_AGENT})
    with urlopen(request, timeout=YOUTUBE_TIMEOUT) as response:
        return response.read().decode('utf-8', errors='replace')


def _fetch_json(url, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': YOUTUBE_USER_AGENT},
    )
    with urlopen(request, timeout=YOUTUBE_TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8', errors='replace'))


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


def _youtube_initial_data(html):
    markers = ('var ytInitialData = ', 'window["ytInitialData"] = ', 'ytInitialData = ')
    decoder = json.JSONDecoder()
    for marker in markers:
        position = html.find(marker)
        if position < 0:
            continue
        start = position + len(marker)
        try:
            data, _ = decoder.raw_decode(html[start:].lstrip())
        except json.JSONDecodeError:
            continue
        return data
    return {}


def _innertube_context(html):
    api_key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"(?P<key>[^"]+)"', html)
    version_match = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION"\s*:\s*"(?P<version>[^"]+)"', html)
    if not api_key_match:
        return '', {}
    return api_key_match.group('key'), {
        'client': {
            'clientName': 'WEB',
            'clientVersion': version_match.group('version') if version_match else '2.20260905.01.00',
        },
    }


def _walk_youtube_data(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_youtube_data(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_youtube_data(value)


def _youtube_text(value):
    if not isinstance(value, dict):
        return ''
    if value.get('content'):
        return _clean_youtube_text(value.get('content'))
    if value.get('simpleText'):
        return _clean_youtube_text(value.get('simpleText'))
    runs = value.get('runs')
    if isinstance(runs, list):
        return _clean_youtube_text(''.join(run.get('text', '') for run in runs if isinstance(run, dict)))
    return ''


def _bucket_from_relative_text(value):
    text = _clean_youtube_text(value).lower()
    match = re.search(r'(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago', text)
    if not match:
        return ''
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith(('minute', 'hour')):
        return 'today'
    if unit.startswith('day'):
        if amount == 1:
            return 'yesterday'
        if amount <= 7:
            return 'week'
        if amount <= 30:
            return 'month'
        return 'old'
    if unit.startswith('week'):
        return 'week' if amount == 1 else 'month'
    return 'month' if amount == 1 else 'old'


def _initial_video_items_from_data(data, url_prefix):
    items = []
    seen = set()
    for node in _walk_youtube_data(data):
        shorts_lockup = node.get('shortsLockupViewModel')
        if isinstance(shorts_lockup, dict):
            endpoint = (
                shorts_lockup.get('onTap', {})
                .get('innertubeCommand', {})
                .get('reelWatchEndpoint', {})
            )
            video_id = endpoint.get('videoId') or (shorts_lockup.get('entityId', '').rsplit('-', 1)[-1])
            if not video_id or video_id in seen:
                continue
            if url_prefix != '/shorts':
                continue
            title = _clean_youtube_text((shorts_lockup.get('accessibilityText') or '').split(',')[0])
            seen.add(video_id)
            items.append({
                'id': video_id,
                'title': title,
                'published': '',
                'bucket': '',
            })
            continue
        lockup = node.get('lockupViewModel')
        if isinstance(lockup, dict):
            video_id = lockup.get('contentId')
            content_type = lockup.get('contentType')
            if not video_id or video_id in seen:
                continue
            if url_prefix == '/watch' and content_type != 'LOCKUP_CONTENT_TYPE_VIDEO':
                continue
            metadata = lockup.get('metadata', {}).get('lockupMetadataViewModel', {})
            title = _youtube_text(metadata.get('title'))
            published = ''
            bucket = ''
            content_metadata = metadata.get('metadata', {}).get('contentMetadataViewModel', {})
            for row in content_metadata.get('metadataRows', []):
                for part in row.get('metadataParts', []):
                    part_text = _youtube_text(part.get('text'))
                    published = _published_from_relative_text(part_text)
                    bucket = _bucket_from_relative_text(part_text)
                    if published:
                        break
                if published:
                    break
            seen.add(video_id)
            items.append({
                'id': video_id,
                'title': title,
                'published': published,
                'bucket': bucket,
            })
            continue
        renderer = node.get('videoRenderer') or node.get('gridVideoRenderer') or node.get('reelItemRenderer')
        if not isinstance(renderer, dict):
            continue
        video_id = renderer.get('videoId')
        if not video_id or video_id in seen:
            continue
        navigation = renderer.get('navigationEndpoint', {})
        url = (
            navigation.get('commandMetadata', {})
            .get('webCommandMetadata', {})
            .get('url', '')
        )
        if url and not url.startswith(url_prefix):
            continue
        title = _youtube_text(renderer.get('title')) or _youtube_text(renderer.get('headline'))
        published_text = _youtube_text(renderer.get('publishedTimeText')) or _youtube_text(renderer.get('shortBylineText'))
        published = _published_from_relative_text(published_text)
        bucket = _bucket_from_relative_text(published_text)
        seen.add(video_id)
        items.append({
            'id': video_id,
            'title': title,
            'published': published,
            'bucket': bucket,
        })
    return items


def _initial_video_items_from_html(html, url_prefix):
    return _initial_video_items_from_data(_youtube_initial_data(html), url_prefix)


def _continuation_tokens_from_data(data):
    tokens = []
    for node in _walk_youtube_data(data):
        command = node.get('continuationCommand')
        if isinstance(command, dict) and command.get('token') and command['token'] not in tokens:
            tokens.append(command['token'])
    return tokens


def _continuation_items_from_html(html, url_prefix, max_pages=8):
    api_key, context = _innertube_context(html)
    if not api_key:
        return []
    tokens = _continuation_tokens_from_data(_youtube_initial_data(html))
    items = []
    seen_ids = set()
    seen_tokens = set()
    today = timezone.localdate()
    for _ in range(max_pages):
        if not tokens:
            break
        token = tokens.pop(0)
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        try:
            data = _fetch_json(YOUTUBE_BROWSE_URL.format(api_key=api_key), {
                'context': context,
                'continuation': token,
            })
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            break
        batch = []
        for item in _initial_video_items_from_data(data, url_prefix):
            if item['id'] in seen_ids:
                continue
            seen_ids.add(item['id'])
            items.append(item)
            batch.append(item)
        for next_token in _continuation_tokens_from_data(data):
            if next_token not in seen_tokens and next_token not in tokens:
                tokens.append(next_token)
        dates = []
        for item in batch:
            published_at = parse_datetime(item.get('published') or '')
            if published_at:
                dates.append(timezone.localdate(published_at))
        if dates and max(dates) < today - timezone.timedelta(days=30):
            break
    return items


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


def _youtube_page_publish_date(video_id, is_short=False):
    cache_key = f'{YOUTUBE_CACHE_VERSION}:youtube-page-published:{"short" if is_short else "video"}:{video_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f'https://www.youtube.com/shorts/{video_id}' if is_short else f'https://www.youtube.com/watch?v={video_id}'
    try:
        html = _fetch_text(url)
    except (OSError, URLError, ValueError):
        cache.set(cache_key, '', 60 * 30)
        return ''

    patterns = (
        r'<meta itemprop="uploadDate" content="(?P<date>[^"]+)"',
        r'<meta itemprop="datePublished" content="(?P<date>[^"]+)"',
        r'"publishDate":"(?P<date>[^"]+)"',
        r'"uploadDate":"(?P<date>[^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            published = _clean_youtube_text(match.group('date'))
            cache.set(cache_key, published, 60 * 60 * 24)
            return published

    cache.set(cache_key, '', 60 * 30)
    return ''


def fetch_youtube_channel_videos(channel_url, limit=None):
    channel_id = extract_youtube_channel_id(channel_url)
    if not channel_id:
        return []

    cache_key = f'{YOUTUBE_CACHE_VERSION}:youtube-feed:{channel_id}:{limit or "all"}'
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
                        'bucket': '',
                    })

    try:
        html = _fetch_text(_channel_tab_url(channel_url, channel_id, 'videos'))
    except (OSError, URLError, ValueError):
        html = ''
    if html:
        existing_ids = {video['id'] for video in videos}
        initial_items = _initial_video_items_from_html(html, '/watch')
        for item in initial_items:
            if item['id'] in existing_ids:
                for video in videos:
                    if video['id'] == item['id'] and item.get('published'):
                        video['published'] = item['published']
                continue
            title = item.get('title') or _youtube_oembed_title(item['id']) or 'YouTube video'
            videos.append({
                'id': item['id'],
                'title': title,
                'description': '',
                'thumbnail': f'https://i.ytimg.com/vi/{item["id"]}/hqdefault.jpg',
                'url': f'https://www.youtube.com/watch?v={item["id"]}',
                'embed_url': f'https://www.youtube.com/embed/{item["id"]}?enablejsapi=1&rel=0',
                'published': item.get('published', ''),
                'bucket': item.get('bucket', ''),
            })
            existing_ids.add(item['id'])
            if limit and len(videos) >= limit:
                break
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
                'bucket': '',
            })
            existing_ids.add(video_id)
            if limit and len(videos) >= limit:
                break
        for item in _continuation_items_from_html(html, '/watch'):
            if item['id'] in existing_ids:
                continue
            title = item.get('title') or _youtube_oembed_title(item['id']) or 'YouTube video'
            videos.append({
                'id': item['id'],
                'title': title,
                'description': '',
                'thumbnail': f'https://i.ytimg.com/vi/{item["id"]}/hqdefault.jpg',
                'url': f'https://www.youtube.com/watch?v={item["id"]}',
                'embed_url': f'https://www.youtube.com/embed/{item["id"]}?enablejsapi=1&rel=0',
                'published': item.get('published', ''),
                'bucket': item.get('bucket', ''),
            })
            existing_ids.add(item['id'])
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

    cache_key = f'{YOUTUBE_CACHE_VERSION}:youtube-shorts:{channel_id}:{limit or "all"}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        html = _fetch_text(_channel_shorts_url(channel_url, channel_id))
    except (OSError, URLError, ValueError):
        cache.set(cache_key, [], 60 * 5)
        return []

    initial_items = _initial_video_items_from_html(html, '/shorts')
    titles = _shorts_titles_from_html(html)
    published_dates = _shorts_published_from_html(html)
    for item in initial_items:
        if item.get('title'):
            titles[item['id']] = item['title']
        if item.get('published'):
            published_dates[item['id']] = item['published']
    continuation_items = []
    for item in continuation_items:
        if item.get('title'):
            titles[item['id']] = item['title']
        if item.get('published'):
            published_dates[item['id']] = item['published']
    video_metadata = {}
    for item in fetch_youtube_channel_videos(channel_url):
        video_metadata[item['id']] = item

    seen = set()
    shorts = []
    ordered_ids = [item['id'] for item in initial_items] + _shorts_ids_from_html(html) + [item['id'] for item in continuation_items]
    if limit:
        ordered_ids = ordered_ids[:limit]
    missing_published_ids = []
    for video_id in ordered_ids:
        if video_id in seen:
            continue
        seen.add(video_id)
        metadata = video_metadata.get(video_id, {})
        title = titles.get(video_id) or metadata.get('title') or _youtube_oembed_title(video_id, is_short=True) or 'YouTube short'
        published = published_dates.get(video_id) or metadata.get('published', '')
        if not published:
            missing_published_ids.append(video_id)
        shorts.append({
            'id': video_id,
            'title': title,
            'url': f'https://www.youtube.com/shorts/{video_id}',
            'embed_url': f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&rel=0',
            'published': published,
            'bucket': metadata.get('bucket', ''),
        })
        if limit and len(shorts) >= limit:
            break

    if missing_published_ids:
        fetched_dates = {}
        with ThreadPoolExecutor(max_workers=12) as executor:
            future_map = {
                executor.submit(_youtube_page_publish_date, video_id, True): video_id
                for video_id in missing_published_ids[:60]
            }
            for future in as_completed(future_map):
                fetched_dates[future_map[future]] = future.result()
        for item in shorts:
            if not item.get('published') and fetched_dates.get(item['id']):
                item['published'] = fetched_dates[item['id']]

    cache.set(cache_key, json.loads(json.dumps(shorts)), 60 * 30)
    return shorts
