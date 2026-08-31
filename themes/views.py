from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.models import user_can_access_tenant

from .forms import TenantBrandingForm, ThemeActivationForm
from .models import ThemeActivation
from .services import get_or_create_branding, get_or_create_theme_activation


def _require_tenant_user(request):
    if not user_can_access_tenant(request.user, request.tenant):
        raise PermissionDenied("You do not have access to this tenant.")


@login_required
def theme_selector(request):
    _require_tenant_user(request)
    activation = get_or_create_theme_activation(request.tenant)
    branding = get_or_create_branding(request.tenant)
    theme_form = ThemeActivationForm(request.POST or None, instance=activation)
    branding_form = TenantBrandingForm(request.POST or None, request.FILES or None, instance=branding)
    if request.method == 'POST' and theme_form.is_valid() and branding_form.is_valid():
        theme_form.save()
        branding_form.save()
        return redirect('themes:theme_selector')
    return render(request, 'themes/selector.html', {
        'theme_form': theme_form,
        'branding_form': branding_form,
        'themes': ThemeActivation.ThemeKey.choices,
        'activation': activation,
    })


@login_required
@require_POST
def activate_theme(request, theme_key):
    _require_tenant_user(request)
    allowed = {choice[0] for choice in ThemeActivation.ThemeKey.choices}
    if theme_key not in allowed:
        raise PermissionDenied("Unsupported theme.")
    activation = get_or_create_theme_activation(request.tenant)
    activation.active_theme = theme_key
    activation.draft_theme = theme_key
    activation.save()
    return redirect('themes:theme_selector')
