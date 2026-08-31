from django.core.exceptions import DisallowedHost

from .models import TenantDomain, normalize_hostname


class TenantResolutionMiddleware:
    """Resolve request.tenant from the normalized HTTP host."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        request.tenant_domain = None
        try:
            hostname = normalize_hostname(request.get_host())
        except DisallowedHost:
            raise

        if hostname:
            domain = (
                TenantDomain.objects.select_related('tenant')
                .filter(domain=hostname, status=TenantDomain.Status.ACTIVE)
                .first()
            )
            if domain and domain.tenant.status in {'trial', 'active', 'past_due'}:
                request.tenant_domain = domain
                request.tenant = domain.tenant
        return self.get_response(request)
