from django.http import HttpResponse
from xml.sax.saxutils import escape

from .services import absolute_url, sitemap_items


def robots_txt(request):
    tenant = getattr(request, 'tenant', None)
    sitemap_url = absolute_url(tenant, '/sitemap.xml') if tenant else '/sitemap.xml'
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        "Allow: /static/",
        "Allow: /media/",
        f"Sitemap: {sitemap_url}",
        "",
    ])
    return HttpResponse(body, content_type='text/plain')


def sitemap_xml(request):
    tenant = request.tenant
    rows = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in sitemap_items(tenant):
        rows.append(f"<url><loc>{escape(loc)}</loc><lastmod>{lastmod.date().isoformat()}</lastmod></url>")
    rows.append('</urlset>')
    return HttpResponse("\n".join(rows), content_type='application/xml')


def news_sitemap_xml(request):
    tenant = request.tenant
    rows = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">',
    ]
    from news.models import NewsArticle

    articles = NewsArticle.objects.for_tenant(tenant).filter(status=NewsArticle.Status.PUBLISHED).select_related('author')[:1000]
    for article in articles:
        rows.append(
            f"<url><loc>{escape(absolute_url(tenant, f'/articles/{article.slug}/'))}</loc>"
            f"<news:news><news:publication><news:name>{escape(tenant.publication_name)}</news:name><news:language>{escape(tenant.default_language)}</news:language></news:publication>"
            f"<news:publication_date>{article.published_at.date().isoformat() if article.published_at else article.created_at.date().isoformat()}</news:publication_date>"
            f"<news:title>{escape(article.title)}</news:title></news:news></url>"
        )
    rows.append('</urlset>')
    return HttpResponse("\n".join(rows), content_type='application/xml')
