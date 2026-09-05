from django.urls import path

from . import views

app_name = 'tenants'

urlpatterns = [
    path('saas-admin/', views.saas_admin_dashboard, name='saas_admin_dashboard'),
    path('site/<slug:tenant_slug>/', views.public_tenant_site, name='public_tenant_site'),
    path('site/<slug:tenant_slug>/category/<slug:category_slug>/', views.public_tenant_category, name='public_tenant_category'),
    path('site/<slug:tenant_slug>/<slug:page>/', views.public_tenant_page, name='public_tenant_page'),
    path('latest-news/', views.public_domain_page, {'page': 'latest-news'}, name='public_latest_news'),
    path('top-stories/', views.public_domain_page, {'page': 'top-stories'}, name='public_top_stories'),
    path('blogs/', views.public_domain_page, {'page': 'blogs'}, name='public_blogs'),
    path('videos/', views.public_domain_page, {'page': 'videos'}, name='public_videos'),
    path('live-tv/', views.public_domain_page, {'page': 'live-tv'}, name='public_live_tv'),
    path('contact/', views.public_domain_page, {'page': 'contact'}, name='public_contact'),
    path('category/<slug:category_slug>/', views.public_domain_category, name='public_domain_category'),
    path('register/', views.visitor_register, name='visitor_register'),
    path('articles/<uuid:uuid>/', views.public_article_detail, name='public_article_detail'),
    path('articles/<slug:slug>/', views.public_article_slug_redirect, name='public_article_slug_redirect'),
    path('dashboard/', views.tenant_dashboard, name='tenant_dashboard'),
    path('dashboard/reporters/', views.reporter_list, name='reporter_list'),
    path('dashboard/reporters/add/', views.reporter_create, name='reporter_create'),
    path('settings/<uuid:uuid>/', views.tenant_settings, name='tenant_settings'),
    path('<slug:page>/', views.public_domain_page, name='public_static_page'),
]
