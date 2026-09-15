from django.contrib import admin
from .models import Campaign, Post, word_count

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'starts_on', 'days', 'active']

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['topic', 'language', 'status', 'scheduled_at', 'words']
    list_filter = ['campaign', 'language', 'status']
    search_fields = ['title', 'topic', 'content']
    readonly_fields = ['published_at', 'updated_at']
    date_hierarchy = 'scheduled_at'

    @admin.display(description='Words')
    def words(self, obj):
        return word_count(obj.content)

