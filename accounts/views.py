from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from subscriptions.entitlements import get_effective_entitlements
from subscriptions.forms import disable_autofill
from subscriptions.views import _customer_tenant_context

from .forms import ProfileForm


@login_required
def profile(request):
    tenant, subscription, onboarding = _customer_tenant_context(request.user)
    if request.method == 'POST':
        if 'change_password' in request.POST:
            form = ProfileForm(instance=request.user)
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Password updated.')
                return redirect('accounts:profile')
        else:
            form = ProfileForm(request.POST, instance=request.user)
            password_form = PasswordChangeForm(request.user)
            if form.is_valid():
                form.save()
                messages.success(request, 'Profile updated.')
                return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)
    disable_autofill(password_form.fields)

    entitlements = get_effective_entitlements(tenant) if tenant else {}
    return render(
        request,
        'accounts/profile.html',
        {
            'form': form,
            'password_form': password_form,
            'tenant': tenant,
            'subscription': subscription,
            'onboarding': onboarding,
            'entitlements': entitlements,
        },
    )
