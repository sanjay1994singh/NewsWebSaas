from django.urls import path

from . import views

app_name = 'news'

urlpatterns = [
    path('articles/<uuid:uuid>/', views.article_detail, name='article_detail'),
    path('search/', views.tenant_article_search, name='tenant_article_search'),
    path('breaking/', views.tenant_breaking_news, name='tenant_breaking_news'),
]
