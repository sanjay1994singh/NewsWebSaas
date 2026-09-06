"""First-party platform tracking. Never store IPs, query strings or raw user agents."""
import logging
import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone

from .models import PlatformVisitor, PlatformVisit

logger = logging.getLogger(__name__)
COOKIE = 'pnx_platform_visitor'
SESSION_COOKIE = 'pnx_platform_visit'
VISITOR_AGE = 60 * 60 * 24 * 365
SESSION_AGE = 60 * 30


def tracking_allowed(request):
    return (getattr(settings, 'PLATFORM_VISITOR_TRACKING_ENABLED', True)
            and not getattr(request, 'tenant', None)
            and request.META.get('HTTP_DNT') != '1'
            and request.META.get('HTTP_SEC_GPC') != '1'
            and not any(word in request.META.get('HTTP_USER_AGENT', '').lower()
                        for word in ('bot', 'crawler', 'spider', 'headless')))


def cookie_uuid(request, name, age):
    value = request.get_signed_cookie(name, default='', salt=name, max_age=age)
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid4()


def identity(request):
    if not hasattr(request, '_platform_identity'):
        request._platform_identity = (
            cookie_uuid(request, COOKIE, VISITOR_AGE),
            cookie_uuid(request, SESSION_COOKIE, SESSION_AGE),
        )
    return request._platform_identity


def visitor_for_request(request):
    visitor_id, _ = identity(request)
    visitor, _ = PlatformVisitor.objects.get_or_create(pk=visitor_id)
    PlatformVisitor.objects.filter(pk=visitor.pk).update(last_seen=timezone.now())
    return visitor


def set_tracking_cookies(request, response):
    visitor_id, session_id = identity(request)
    for name, value, age in ((COOKIE, visitor_id, VISITOR_AGE), (SESSION_COOKIE, session_id, SESSION_AGE)):
        response.set_signed_cookie(name, str(value), salt=name, max_age=age,
                                   httponly=True, secure=request.is_secure(), samesite='Lax')
    # A visitor-specific cookie must never be shared through a page cache.
    from django.utils.cache import patch_cache_control, patch_vary_headers
    patch_cache_control(response, private=True, no_store=True)
    patch_vary_headers(response, ['Cookie'])


def request_details(request):
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    device = ('tablet' if 'ipad' in ua or 'tablet' in ua or ('android' in ua and 'mobile' not in ua)
              else 'mobile' if 'mobile' in ua or 'iphone' in ua else 'desktop' if ua else 'unknown')
    browser = next((label for token, label in [('edg', 'Edge'), ('opr/', 'Opera'), ('samsungbrowser', 'Samsung Internet'),
                    ('firefox', 'Firefox'), ('fxios', 'Firefox'), ('chrome', 'Chrome'), ('crios', 'Chrome'), ('safari', 'Safari')]
                    if token in ua), 'Other')
    try:
        referrer = (urlsplit(request.META.get('HTTP_REFERER', '')).hostname or '')[:255].lower()
        if referrer == request.get_host().split(':')[0].lower():
            referrer = ''
    except ValueError:
        referrer = ''
    return {'device_type': device, 'browser': browser, 'referrer_domain': referrer}


class PlatformVisitorMiddleware:
    PUBLIC_VIEWS = {
        'home', 'public_saas_landing', 'public_saas_signup', 'about_us', 'contact_us',
        'privacy_policy', 'terms_and_conditions', 'refund_policy', 'billing_policy', 'grievance',
        'subscriptions:landing', 'subscriptions:signup', 'accounts:login',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        was_authenticated = request.user.is_authenticated
        response = self.get_response(request)
        match = getattr(request, 'resolver_match', None)
        name = match.view_name if match else ''
        if name not in self.PUBLIC_VIEWS or not tracking_allowed(request):
            return response
        kind = None
        if request.method == 'GET' and response.status_code == 200 and response.get('Content-Type', '').startswith('text/html'):
            kind = 'page'
        elif (request.method == 'POST' and response.status_code in (301, 302, 303)
              and not was_authenticated and request.user.is_authenticated):
            if name == 'accounts:login':
                kind = 'login'
            elif name in {'public_saas_signup', 'subscriptions:signup'}:
                kind = 'signup'
        if kind:
            try:
                with transaction.atomic():
                    visitor = visitor_for_request(request)
                    _, session_id = identity(request)
                    returning = visitor.visits.exclude(session_id=session_id).exists()
                    PlatformVisit.objects.create(
                        visitor=visitor, session_id=session_id, kind=kind,
                        user=request.user if request.user.is_authenticated else None,
                        path=request.path[:500], is_returning=returning, **request_details(request))
                set_tracking_cookies(request, response)
            except DatabaseError:
                logger.exception('Platform visitor tracking failed')
        elif getattr(request, '_platform_enquiry_saved', False):
            set_tracking_cookies(request, response)
        return response
