from django.contrib import admin

from .models import AuthorProfile, BreakingNews, NewsArticle, Tag


@admin.register(AuthorProfile)
class AuthorProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'tenant', 'slug', 'designation', 'is_public')
    list_filter = ('is_public',)
    search_fields = ('display_name', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'user')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'slug', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant',)


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'category', 'author', 'status', 'published_at', 'is_breaking')
    list_filter = ('status', 'is_breaking', 'is_featured', 'is_trending', 'is_editor_pick')
    search_fields = ('title', 'slug', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'category', 'author', 'reporters', 'tags')
    filter_horizontal = ('reporters', 'tags')


@admin.register(BreakingNews)
class BreakingNewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'article', 'ticker_order', 'is_active', 'starts_at', 'ends_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'article__title', 'tenant__publication_name')
    autocomplete_fields = ('tenant', 'article')
