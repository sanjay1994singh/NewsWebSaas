import ipaddress
import re
from urllib.parse import urlparse

from django.core.exceptions import ValidationError

from .models import normalize_hostname


DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def validate_public_domain(value):
    raw = (value or '').strip()
    if '://' in raw:
        parsed = urlparse(raw)
        if parsed.scheme or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValidationError("Enter a hostname only, not a URL or path.")
        raw = parsed.netloc
    if '/' in raw or '?' in raw or '#' in raw:
        raise ValidationError("Enter a hostname only, not a URL or path.")
    domain = normalize_hostname(raw)
    if not domain:
        raise ValidationError("Domain is required.")
    if domain in {'localhost', 'local'} or domain.endswith('.localhost') or domain.endswith('.local'):
        raise ValidationError("Localhost and local domains are not allowed.")
    try:
        ip = ipaddress.ip_address(domain)
    except ValueError:
        ip = None
    if ip is not None:
        raise ValidationError("Enter a domain name, not an IP address.")
    if not DOMAIN_RE.match(domain):
        raise ValidationError("Enter a valid public domain.")
    return domain
