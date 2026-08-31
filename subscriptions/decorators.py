from functools import wraps

from django.http import JsonResponse

from .entitlements import tenant_has_feature


def feature_required(feature_code):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            tenant = getattr(request, 'tenant', None)
            if tenant is None:
                tenant = kwargs.get('tenant')
            if tenant is None or not tenant_has_feature(tenant, feature_code):
                return JsonResponse(
                    {'detail': 'This feature is not enabled for the current tenant.'},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
