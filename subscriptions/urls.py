from django.urls import path

from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('saas/', views.landing_page, name='landing'),
    path('saas/signup/', views.signup, name='signup'),
    path('saas/checkout/<uuid:acquisition_id>/', views.checkout, name='checkout'),
    path('saas/checkout/<uuid:acquisition_id>/verify/', views.verify_subscription, name='verify_subscription'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('onboarding/review-status/', views.review_status, name='review_status'),
    path('onboarding/ready-to-publish/', views.ready_to_publish, name='ready_to_publish'),
    path('onboarding/review/<uuid:onboarding_id>/', views.onboarding_review, name='onboarding_review'),
    path('account/billing/', views.billing_dashboard, name='billing_dashboard'),
    path('account/status/', views.account_status, name='account_status'),
    path('account/billing/change-plan/', views.change_plan, name='change_plan'),
    path('account/billing/add-ons/<uuid:add_on_id>/activate/', views.activate_add_on, name='activate_add_on'),
    path('account/billing/add-ons/<int:tenant_add_on_id>/cancel/', views.cancel_add_on, name='cancel_add_on'),
    path('webhooks/razorpay/', views.razorpay_webhook, name='razorpay_webhook'),
    path('features/<slug:tenant_slug>/<slug:feature_code>/check/', views.feature_access_check, name='feature_access_check'),
]
