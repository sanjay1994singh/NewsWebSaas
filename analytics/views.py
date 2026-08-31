from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from core.models import user_can_access_tenant
from tenants.views import is_platform_admin

from .services import platform_metrics, tenant_analytics


@login_required
@user_passes_test(is_platform_admin)
def super_admin_dashboard(request):
    return render(request, 'analytics/super_admin_dashboard.html', {'metrics': platform_metrics()})


@login_required
def tenant_analytics_dashboard(request):
    if not user_can_access_tenant(request.user, request.tenant):
        raise PermissionDenied("You do not have access to this tenant.")
    return render(request, 'analytics/tenant_dashboard.html', {'analytics': tenant_analytics(request.tenant)})

# Create your views here.
