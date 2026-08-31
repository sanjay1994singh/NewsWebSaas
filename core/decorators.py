from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import user_can_access_tenant


def tenant_permission_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not user_can_access_tenant(request.user, getattr(request, 'tenant', None), roles or None):
                raise PermissionDenied("You do not have access to this tenant.")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
