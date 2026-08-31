from django.contrib import admin

from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'slug', 'parent', 'menu_order', 'is_active', 'show_in_menu')
    list_filter = ('is_active', 'show_in_menu', 'show_on_homepage')
    search_fields = ('name', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'parent')
