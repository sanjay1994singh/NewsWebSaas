from .models import TenantBranding, ThemeActivation


def get_or_create_branding(tenant):
    return TenantBranding.objects.get_or_create(
        tenant=tenant,
        defaults={'publication_name': tenant.publication_name},
    )[0]


def get_or_create_theme_activation(tenant):
    return ThemeActivation.objects.get_or_create(tenant=tenant)[0]
