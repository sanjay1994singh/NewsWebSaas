from django.urls import path

from . import views

app_name = 'domains'

urlpatterns = [
    path('settings/domains/', views.domain_list, name='domain_list'),
    path('settings/domains/add/', views.add_domain, name='add_domain'),
    path('settings/domains/<int:domain_id>/', views.domain_detail, name='domain_detail'),
    path('settings/domains/<int:domain_id>/verify/', views.verify_domain, name='verify_domain'),
    path('settings/domains/<int:domain_id>/primary/', views.make_primary, name='make_primary'),
    path('settings/domains/<int:domain_id>/ssl/', views.provision_ssl, name='provision_ssl'),
]
