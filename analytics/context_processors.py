"""Google Analytics configuration for public Press Nexa pages only."""
import re
from urllib.parse import urlsplit

from django.conf import settings

from .tracking import PlatformVisitorMiddleware


def google_analytics(request):
    measurement_id = getattr(settings, 'GOOGLE_ANALYTICS_MEASUREMENT_ID', '').strip()
    match = getattr(request, 'resolver_match', None)
    if (not re.fullmatch(r'G-[A-Z0-9]{10}', measurement_id)
            or not getattr(settings, 'GOOGLE_ANALYTICS_ENABLED', True)
            or getattr(request, 'tenant', None)
            or not match or match.view_name not in PlatformVisitorMiddleware.PUBLIC_VIEWS
            or request.method != 'GET'
            or request.META.get('HTTP_DNT') == '1'
            or request.META.get('HTTP_SEC_GPC') == '1'):
        return {}
    # Keep local development, preview hosts and tenant sites out of the real property.
    platform_host = urlsplit(settings.SITE_BASE_URL).hostname
    if urlsplit(request.build_absolute_uri('/')).hostname != platform_host:
        return {}
    return {'google_analytics_id': measurement_id}
