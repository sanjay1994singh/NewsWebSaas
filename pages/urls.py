from django.urls import path

from . import views

app_name = 'pages'

urlpatterns = [
    path('appearance/homepage/', views.homepage_builder, name='homepage_builder'),
    path('appearance/homepage/preview/', views.homepage_preview, name='homepage_preview'),
    path('appearance/homepage/save/', views.save_homepage_draft, name='save_homepage_draft'),
    path('appearance/homepage/add-block/', views.add_block, name='add_block'),
    path('appearance/homepage/<int:block_id>/remove/', views.remove_block, name='remove_block'),
    path('appearance/homepage/<int:block_id>/duplicate/', views.duplicate_block, name='duplicate_block'),
    path('appearance/homepage/publish/', views.publish_homepage, name='publish_homepage'),
    path('appearance/homepage/restore-published/', views.restore_published, name='restore_published'),
    path('appearance/homepage/restore-default/', views.restore_default, name='restore_default'),
    path('appearance/menus/<str:location>/', views.menu_builder, name='menu_builder'),
    path('site-pages/', views.tenant_static_page_list, name='tenant_static_page_list'),
    path('site-pages/<int:page_id>/edit/', views.tenant_static_page_edit, name='tenant_static_page_edit'),
]
