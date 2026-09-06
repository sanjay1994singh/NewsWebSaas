from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse
from django.db import transaction
from django.contrib.auth import get_user_model

from core.models import user_can_access_tenant
from subscriptions.entitlements import get_effective_entitlements
from subscriptions.forms import disable_autofill
from subscriptions.views import _customer_tenant_context

from .forms import IdentifierAuthenticationForm, ProfileForm


class TenantAwareLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = IdentifierAuthenticationForm

    def form_valid(self, form):
        response = super().form_valid(form)
        tenant = getattr(self.request, 'tenant', None)
        if tenant and not user_can_access_tenant(self.request.user, tenant):
            logout(self.request)
            messages.error(self.request, 'Aapka account is site par registered nahi hai. Is site ke dashboard me access ke liye registered owner ya staff account se login karein.')
            return redirect(f"{reverse('accounts:login')}?next=/dashboard/")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = getattr(self.request, 'tenant', None)
        if tenant:
            context['tenant_register_url'] = reverse('tenants:visitor_register')
            context['tenant_register_label'] = 'Register as visitor'
        return context


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
            with transaction.atomic():
                profile_user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                previous_email = profile_user.email.strip()
                form = ProfileForm(request.POST, instance=profile_user)
                password_form = PasswordChangeForm(request.user)
                if form.is_valid():
                    user = form.save()
                    if not previous_email and user.email.strip():
                        from subscriptions.models import CustomerAcquisition
                        from tenants.models import Tenant
                        from subscriptions.welcome import send_profile_details
                        CustomerAcquisition.objects.filter(user=user, email='').update(email=user.email)
                        Tenant.objects.filter(owner=user, email='').update(email=user.email)
                        transaction.on_commit(lambda: send_profile_details(user.pk))
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
