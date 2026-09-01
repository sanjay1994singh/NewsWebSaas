from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from subscriptions.entitlements import get_effective_entitlements
from subscriptions.views import _customer_tenant_context

from .forms import ProfileForm


@login_required
def profile(request):
    tenant, subscription, onboarding = _customer_tenant_context(request.user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)

    entitlements = get_effective_entitlements(tenant) if tenant else {}
    return render(
        request,
        'accounts/profile.html',
        {
            'form': form,
            'tenant': tenant,
            'subscription': subscription,
            'onboarding': onboarding,
            'entitlements': entitlements,
        },
    )
