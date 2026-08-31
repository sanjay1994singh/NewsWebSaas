from django.urls import path

from . import views

app_name = 'tenants'

urlpatterns = [
    path('saas-admin/', views.saas_admin_dashboard, name='saas_admin_dashboard'),
    path('dashboard/', views.tenant_dashboard, name='tenant_dashboard'),
    path('settings/<uuid:uuid>/', views.tenant_settings, name='tenant_settings'),
]
