from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from core.models import user_can_access_tenant
from tenants.models import Tenant


@login_required
def tenant_summary(request, uuid):
    try:
        tenant = Tenant.objects.get(uuid=uuid)
    except Tenant.DoesNotExist:
        return JsonResponse({'detail': 'Not found'}, status=404)
    if not user_can_access_tenant(request.user, tenant):
        raise PermissionDenied("You do not have access to this tenant.")
    return JsonResponse({
        'uuid': str(tenant.uuid),
        'publication_name': tenant.publication_name,
        'status': tenant.status,
    })
