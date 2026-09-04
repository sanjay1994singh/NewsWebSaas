from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.TenantAwareLoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(next_page='home'), name='logout'),
    path('profile/', views.profile, name='profile'),
]
