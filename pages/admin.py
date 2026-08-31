from django.contrib import admin

from .models import FooterSection, HomepageBlock, HomepageLayout, Menu, MenuItem, Page


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'slug', 'page_type', 'is_published', 'updated_at')
    list_filter = ('page_type', 'is_published')
    search_fields = ('title', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)


class HomepageBlockInline(admin.TabularInline):
    model = HomepageBlock
    extra = 0
    autocomplete_fields = ('tenant', 'category')


@admin.register(HomepageLayout)
class HomepageLayoutAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'name', 'status', 'theme_key', 'updated_at')
    list_filter = ('status', 'theme_key')
    search_fields = ('tenant__publication_name', 'name')
    autocomplete_fields = ('tenant', 'published_from')
    inlines = (HomepageBlockInline,)


@admin.register(HomepageBlock)
class HomepageBlockAdmin(admin.ModelAdmin):
    list_display = ('heading', 'tenant', 'layout', 'block_type', 'order', 'is_enabled')
    list_filter = ('block_type', 'is_enabled')
    search_fields = ('heading', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'layout', 'category')


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0
    autocomplete_fields = ('tenant', 'parent', 'category', 'page')


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'location', 'updated_at')
    list_filter = ('location',)
    search_fields = ('name', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)
    inlines = (MenuItemInline,)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('label', 'tenant', 'menu', 'parent', 'link_type', 'order', 'is_enabled')
    list_filter = ('link_type', 'is_enabled')
    search_fields = ('label', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'menu', 'parent', 'category', 'page')


@admin.register(FooterSection)
class FooterSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'order', 'is_enabled')
    list_filter = ('is_enabled',)
    search_fields = ('title', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)
