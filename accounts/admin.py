from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Platform role', {'fields': ('platform_role',)}),
    )
    list_display = ('username', 'email', 'platform_role', 'is_staff', 'is_active')
    list_filter = UserAdmin.list_filter + ('platform_role',)
