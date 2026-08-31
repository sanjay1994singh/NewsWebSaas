from django.contrib import admin

from .models import Tenant, TenantMembership


class TenantMembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0
    autocomplete_fields = ('user',)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('publication_name', 'business_name', 'slug', 'status', 'owner', 'created_at')
    list_filter = ('status', 'onboarding_status', 'country')
    search_fields = ('publication_name', 'business_name', 'slug', 'email')
    autocomplete_fields = ('owner',)
    inlines = (TenantMembershipInline,)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'user', 'role', 'status', 'joined_at')
    list_filter = ('role', 'status')
    search_fields = ('tenant__publication_name', 'user__username', 'user__email')
    autocomplete_fields = ('tenant', 'user')
