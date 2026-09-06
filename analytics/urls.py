from django.urls import path

from . import views

app_name = 'analytics'

urlpatterns = [
    path('saas-admin/visitors/', views.visitor_report, name='visitor_report'),
    path('saas-admin/enquiries/<int:pk>/', views.update_enquiry, name='update_enquiry'),
    path('saas-admin/metrics/', views.super_admin_dashboard, name='super_admin_dashboard'),
    path('dashboard/analytics/', views.tenant_analytics_dashboard, name='tenant_analytics_dashboard'),
]
