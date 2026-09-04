"""config URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from subscriptions import views as subscription_views

urlpatterns = [
    path('', subscription_views.customer_home, name='home'),
    path('profile/', subscription_views.tenant_profile_redirect, name='tenant_profile_redirect'),
    path('saas/', subscription_views.landing_page, name='public_saas_landing'),
    path('saas/signup/', subscription_views.signup, name='public_saas_signup'),
    path('about-us/', subscription_views.about_us, name='about_us'),
    path('contact-us/', subscription_views.policy_page, {'policy_type': 'contact'}, name='contact_us'),
    path('privacy-policy/', subscription_views.policy_page, {'policy_type': 'privacy'}, name='privacy_policy'),
    path('terms-and-conditions/', subscription_views.policy_page, {'policy_type': 'terms'}, name='terms_and_conditions'),
    path('refund-policy/', subscription_views.policy_page, {'policy_type': 'refund'}, name='refund_policy'),
    path('billing-policy/', subscription_views.policy_page, {'policy_type': 'billing'}, name='billing_policy'),
    path('grievance/', subscription_views.policy_page, {'policy_type': 'grievance'}, name='grievance'),
    path('account/', include('accounts.urls')),
    path('', include('seo.urls')),
    path('', include('analytics.urls')),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('cms/', include('news.urls')),
    path('dashboard/', include('pages.urls')),
    path('dashboard/', include('themes.urls')),
    path('dashboard/', include('domains.urls')),
    path('billing/', include('subscriptions.urls')),
    path('', include('epaper.urls')),
    path('', include('tenants.urls')),
]
