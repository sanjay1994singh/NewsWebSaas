from .models import AuditLog


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def record_audit_log(request, action, instance=None, metadata=None, tenant=None, user=None):
    resolved_user = user if user is not None else getattr(request, 'user', None)
    if resolved_user is not None and not resolved_user.is_authenticated:
        resolved_user = None
    resolved_tenant = tenant if tenant is not None else getattr(request, 'tenant', None)
    return AuditLog.objects.create(
        tenant=resolved_tenant,
        user=resolved_user,
        action=action,
        model=instance.__class__.__name__ if instance is not None else '',
        object_id=str(instance.pk) if instance is not None and instance.pk else '',
        ip_address=get_client_ip(request),
        metadata=metadata or {},
    )
