from django.urls import path

from . import views

app_name = 'news'

urlpatterns = [
    path('', views.article_dashboard, name='article_dashboard'),
    path('articles/add/', views.article_create, name='article_create'),
    path('articles/<uuid:uuid>/', views.article_detail, name='article_detail'),
    path('articles/<uuid:uuid>/edit/', views.article_update, name='article_update'),
    path('articles/<uuid:uuid>/delete/', views.article_delete, name='article_delete'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_update, name='category_update'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('uploads/ckeditor/', views.ckeditor_image_upload, name='ckeditor_image_upload'),
    path('search/', views.tenant_article_search, name='tenant_article_search'),
    path('breaking/', views.tenant_breaking_news, name='tenant_breaking_news'),
]
