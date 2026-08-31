def media_for_tenant(tenant):
    from .models import MediaAsset

    return MediaAsset.objects.for_tenant(tenant).select_related('uploaded_by')
