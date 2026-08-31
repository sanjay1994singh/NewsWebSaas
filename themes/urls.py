from django.urls import path

from . import views

app_name = 'themes'

urlpatterns = [
    path('appearance/themes/', views.theme_selector, name='theme_selector'),
    path('appearance/themes/<str:theme_key>/activate/', views.activate_theme, name='activate_theme'),
]
