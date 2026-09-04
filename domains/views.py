from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import user_can_access_tenant
from tenants.models import Tenant, TenantMembership

from .forms import TenantDomainForm
from .models import TenantDomain
from .services import create_domain_for_tenant, enqueue_ssl_provisioning, set_primary_domain, verify_domain_ownership


def _active_tenant_for_user(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        membership = (
            TenantMembership.objects
            .select_related('tenant')
            .filter(user=request.user, status=TenantMembership.Status.ACTIVE)
            .order_by('role', 'created_at')
            .first()
        )
        tenant = membership.tenant if membership else Tenant.objects.filter(owner=request.user).first()
    if not user_can_access_tenant(request.user, tenant):
        raise PermissionDenied("You do not have access to this tenant.")
    request.tenant = tenant
    return tenant


@login_required
def domain_list(request):
    tenant = _active_tenant_for_user(request)
    domains = TenantDomain.objects.for_tenant(tenant).order_by('-is_primary', 'domain')
    return render(request, 'domains/domain_list.html', {'tenant': tenant, 'domains': domains})


@login_required
def add_domain(request):
    tenant = _active_tenant_for_user(request)
    form = TenantDomainForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            domain = create_domain_for_tenant(
                tenant=tenant,
                domain=form.cleaned_data['domain'],
                domain_type=form.cleaned_data['domain_type'],
            )
        except ValidationError as exc:
            form.add_error('domain', exc)
        else:
            return redirect('domains:domain_detail', domain_id=domain.id)
    return render(request, 'domains/add_domain.html', {'tenant': tenant, 'form': form})


@login_required
def domain_detail(request, domain_id):
    tenant = _active_tenant_for_user(request)
    domain = get_object_or_404(TenantDomain.objects.for_tenant(tenant), pk=domain_id)
    return render(request, 'domains/domain_detail.html', {'tenant': tenant, 'domain': domain})


@login_required
@require_POST
def verify_domain(request, domain_id):
    tenant = _active_tenant_for_user(request)
    domain = get_object_or_404(TenantDomain.objects.for_tenant(tenant), pk=domain_id)
    try:
        verify_domain_ownership(domain)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Domain verified.')
    return redirect('domains:domain_detail', domain_id=domain.id)


@login_required
@require_POST
def make_primary(request, domain_id):
    tenant = _active_tenant_for_user(request)
    try:
        set_primary_domain(tenant=tenant, domain_id=domain_id)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    return redirect('domains:domain_list')


@login_required
@require_POST
def provision_ssl(request, domain_id):
    tenant = _active_tenant_for_user(request)
    domain = get_object_or_404(TenantDomain.objects.for_tenant(tenant), pk=domain_id)
    enqueue_ssl_provisioning(domain)
    messages.success(request, 'SSL provisioning queued.')
    return redirect('domains:domain_detail', domain_id=domain.id)

# Create your views here.
