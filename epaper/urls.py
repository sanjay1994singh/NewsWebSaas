from django.urls import path

from . import views

app_name = 'epaper'

urlpatterns = [
    path('dashboard/epaper/<uuid:edition_id>/delete/', views.delete_edition, name='delete_edition'),
    path('dashboard/epaper/progress/', views.processing_status, name='processing_status'),
    path('epaper/', views.public_epaper_home, name='domain_home'),
    path('epaper/<slug:slug>/', views.epaper_reader, name='domain_reader'),
    path('epaper/<slug:slug>/download/', views.download_edition, name='domain_download'),
    path('dashboard/epaper/', views.dashboard, name='dashboard'),
    path('dashboard/epaper/new/', views.create_edition, name='create_edition'),
    path('dashboard/epaper/<uuid:edition_id>/publish/', views.publish_edition, name='publish_edition'),
    path('p/<slug:tenant_slug>/epaper/', views.public_epaper_home, name='public_home'),
    path('p/<slug:tenant_slug>/epaper/<slug:slug>/', views.epaper_reader, name='reader'),
    path('p/<slug:tenant_slug>/epaper/<slug:slug>/download/', views.download_edition, name='download'),
]
