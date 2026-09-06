from django import template
from django.urls import reverse
from epaper.services import can_upload_epaper

register = template.Library()


@register.simple_tag(takes_context=True)
def public_epaper_url(context):
    tenant = context.get('tenant')
    if tenant is None or not can_upload_epaper(tenant):
        return ''
    request = context.get('request')
    domain = getattr(request, 'tenant_domain', None)
    if domain is not None and domain.tenant_id == tenant.pk:
        return reverse('epaper:domain_home')
    return reverse('epaper:public_home', args=[tenant.slug])
