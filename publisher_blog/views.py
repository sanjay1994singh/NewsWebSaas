import json
import math
from urllib.parse import urlencode
from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from xml.sax.saxutils import escape
from .models import public_posts, word_count

def reader_meta(post):
    post.read_minutes = max(1, math.ceil(word_count(post.content) / (170 if post.language == 'hi' else 220)))
    url = settings.SITE_BASE_URL + post.get_absolute_url()
    post.whatsapp_url = 'https://wa.me/?' + urlencode({'text': post.title + '\n' + url})
    return post

def platform_only(request):
    if getattr(request, 'tenant', None) is not None:
        raise Http404

def index(request, language=None):
    platform_only(request)
    posts = public_posts().order_by('-published_at')
    if language:
        if language not in {'hi', 'en'}:
            raise Http404
        posts = posts.filter(language=language)
    page = Paginator(posts, 12).get_page(request.GET.get('page'))
    page.object_list = [reader_meta(post) for post in page.object_list]
    canonical = settings.SITE_BASE_URL + request.path
    if page.number > 1:
        canonical += f'?page={page.number}'
    return render(request, 'publisher_blog/index.html', {
        'page': page, 'language': language or 'hi', 'active_language': language, 'canonical': canonical,
        'title': 'न्यूज़ पब्लिशर गाइड | Press Nexa' if language == 'hi' else 'News Publisher Guides | Press Nexa',
        'description': 'न्यूज़ वेबसाइट, प्लान, वीडियो और ई-पेपर पर उपयोगी गाइड।' if language == 'hi' else 'Practical guides to news websites, Press Nexa plans, video publishing and ePaper.',
        'robots': 'index,follow' if page.paginator.count else 'noindex,follow',
    })

def detail(request, language, slug):
    platform_only(request)
    post = get_object_or_404(public_posts(), language=language, slug=slug)
    reader_meta(post)
    canonical = settings.SITE_BASE_URL + post.get_absolute_url()
    schema = {'@context': 'https://schema.org', '@type': 'BlogPosting', 'headline': post.title,
              'description': post.description, 'inLanguage': post.language,
              'datePublished': post.published_at.isoformat(), 'dateModified': post.updated_at.isoformat(),
              'mainEntityOfPage': canonical, 'author': {'@type': 'Organization', 'name': 'Press Nexa'},
              'publisher': {'@type': 'Organization', 'name': 'Press Nexa', 'url': settings.SITE_BASE_URL}}
    breadcrumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': 'Press Nexa', 'item': settings.SITE_BASE_URL + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': 'हिंदी ब्लॉग' if language == 'hi' else 'English blog', 'item': settings.SITE_BASE_URL + '/blog/' + language + '/'},
        {'@type': 'ListItem', 'position': 3, 'name': post.title, 'item': canonical},
    ]}
    return render(request, 'publisher_blog/detail.html', {
        'post': post, 'language': language, 'title': post.title, 'description': post.description,
        'canonical': canonical, 'schema': json.dumps([schema, breadcrumbs], ensure_ascii=False).replace('<', '\\u003c'),
        'facebook_url': 'https://www.facebook.com/sharer/sharer.php?' + urlencode({'u': canonical}),
        'related': [reader_meta(item) for item in public_posts().filter(language=language).exclude(pk=post.pk).order_by('-published_at')[:3]],
    })

def sitemap(request):
    platform_only(request)
    rows = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in ('/', '/saas/', '/about-us/', '/contact-us/', '/blog/', '/blog/hi/', '/blog/en/'):
        rows.append(f'<url><loc>{escape(settings.SITE_BASE_URL + path)}</loc></url>')
    for post in public_posts().iterator():
        rows.append(f'<url><loc>{escape(settings.SITE_BASE_URL + post.get_absolute_url())}</loc><lastmod>{post.updated_at.date().isoformat()}</lastmod></url>')
    return HttpResponse('\n'.join(rows + ['</urlset>']), content_type='application/xml')

