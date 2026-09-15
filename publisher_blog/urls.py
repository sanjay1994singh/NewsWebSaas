from django.urls import path
from . import views
app_name = 'publisher_blog'
urlpatterns = [
    path('', views.index, name='index'),
    path('sitemap.xml', views.sitemap, name='sitemap'),
    path('<str:language>/', views.index, name='language'),
    path('<str:language>/<slug:slug>/', views.detail, name='detail'),
]

