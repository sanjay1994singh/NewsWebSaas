from django.urls import path

from . import views
from . import v1

app_name = 'api'

urlpatterns = [
    path('tenants/<uuid:uuid>/summary/', views.tenant_summary, name='tenant_summary'),
    path('v1/site-config/', v1.SiteConfigView.as_view(), name='v1_site_config'),
    path('v1/homepage/', v1.HomepageView.as_view(), name='v1_homepage'),
    path('v1/categories/', v1.CategoryListView.as_view(), name='v1_categories'),
    path('v1/articles/', v1.ArticleListView.as_view(), name='v1_articles'),
    path('v1/articles/<slug:slug>/', v1.ArticleDetailView.as_view(), name='v1_article_detail'),
    path('v1/breaking/', v1.BreakingNewsView.as_view(), name='v1_breaking'),
    path('v1/search/', v1.SearchView.as_view(), name='v1_search'),
    path('v1/videos/', v1.VideoListView.as_view(), name='v1_videos'),
    path('v1/live-tv/', v1.LiveTVListView.as_view(), name='v1_live_tv'),
    path('v1/pages/', v1.PageListView.as_view(), name='v1_pages'),
]
