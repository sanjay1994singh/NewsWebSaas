from django.urls import path

from . import views

app_name = 'tenants'

urlpatterns = [
    path('saas-admin/', views.saas_admin_dashboard, name='saas_admin_dashboard'),
    path('site/<slug:tenant_slug>/', views.public_tenant_site, name='public_tenant_site'),
    path('dashboard/', views.tenant_dashboard, name='tenant_dashboard'),
    path('settings/<uuid:uuid>/', views.tenant_settings, name='tenant_settings'),
]
