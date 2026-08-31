from django.urls import path

from . import views

app_name = 'epaper'

urlpatterns = [
    path('dashboard/epaper/', views.dashboard, name='dashboard'),
    path('dashboard/epaper/new/', views.create_edition, name='create_edition'),
    path('dashboard/epaper/<uuid:edition_id>/publish/', views.publish_edition, name='publish_edition'),
    path('p/<slug:tenant_slug>/epaper/', views.public_epaper_home, name='public_home'),
    path('p/<slug:tenant_slug>/epaper/<slug:slug>/', views.epaper_reader, name='reader'),
    path('p/<slug:tenant_slug>/epaper/<slug:slug>/download/', views.download_edition, name='download'),
]
