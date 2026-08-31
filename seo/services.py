import json
from urllib.parse import urljoin

from domains.models import TenantDomain
from news.models import NewsArticle
from pages.models import Page

from .models import TenantSEOSettings


def get_primary_domain(tenant):
    domain = TenantDomain.objects.for_tenant(tenant).filter(is_primary=True, is_verified=True, status=TenantDomain.Status.ACTIVE).first()
    return domain.domain if domain else None


def absolute_url(tenant, path):
    domain = get_primary_domain(tenant)
    if not domain:
        return path
    return urljoin(f"https://{domain}", path)


def get_or_create_seo_settings(tenant):
    return TenantSEOSettings.objects.get_or_create(tenant=tenant)[0]


def robots_value(index=True, follow=True):
    return f"{'index' if index else 'noindex'},{'follow' if follow else 'nofollow'}"


def article_meta(article):
    tenant = article.tenant
    title = article.seo_title or article.title
    description = article.meta_description or article.short_description
    canonical = article.canonical_override or absolute_url(tenant, f"/articles/{article.slug}/")
    return {
        'title': title,
        'description': description,
        'canonical': canonical,
        'robots': robots_value(article.robots_index, article.robots_follow),
        'og_type': 'article',
        'og_title': title,
        'og_description': description,
        'og_url': canonical,
    }


def article_json_ld(article):
    data = {
        '@context': 'https://schema.org',
        '@type': 'NewsArticle',
        'headline': article.title,
        'datePublished': article.published_at.isoformat() if article.published_at else None,
        'dateModified': article.updated_at.isoformat() if article.updated_at else None,
        'author': {'@type': 'Person', 'name': article.author.display_name},
        'publisher': {
            '@type': 'NewsMediaOrganization',
            'name': article.tenant.publication_name,
        },
        'mainEntityOfPage': article_meta(article)['canonical'],
    }
    if article.featured_image:
        data['image'] = [absolute_url(article.tenant, article.featured_image.url)]
    return json.dumps({k: v for k, v in data.items() if v}, ensure_ascii=False)


def seo_audit_article(article):
    checks = []
    if not article.seo_title:
        checks.append('Missing SEO title.')
    if not article.meta_description:
        checks.append('Missing meta description.')
    if article.featured_image and not article.image_alt:
        checks.append('Missing featured image ALT text.')
    if not article.author_id:
        checks.append('Missing author.')
    if article.canonical_override and get_primary_domain(article.tenant) not in article.canonical_override:
        checks.append('Canonical override does not use the tenant primary domain.')
    if article.status == NewsArticle.Status.PUBLISHED and not article.robots_index:
        checks.append('Published article is marked noindex.')
    return checks


def sitemap_items(tenant):
    articles = NewsArticle.objects.for_tenant(tenant).filter(status=NewsArticle.Status.PUBLISHED).select_related('author')
    pages = Page.objects.for_tenant(tenant).filter(is_published=True)
    for article in articles:
        yield absolute_url(tenant, f"/articles/{article.slug}/"), article.updated_at
    for page in pages:
        yield absolute_url(tenant, f"/pages/{page.slug}/"), page.updated_at
