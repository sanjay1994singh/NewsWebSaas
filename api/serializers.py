from rest_framework import serializers

from categories.models import Category
from livetv.models import LiveTVChannel
from news.models import BreakingNews, NewsArticle
from pages.models import Page
from themes.services import get_or_create_branding
from videos.models import Video


class SiteConfigSerializer(serializers.Serializer):
    tenant_public_id = serializers.UUIDField(source='uuid')
    publication_name = serializers.CharField()
    colors = serializers.SerializerMethodField()
    social_links = serializers.SerializerMethodField()
    feature_flags = serializers.SerializerMethodField()

    def get_colors(self, tenant):
        branding = get_or_create_branding(tenant)
        return {'primary': branding.primary_color, 'secondary': branding.secondary_color, 'accent': branding.accent_color}

    def get_social_links(self, tenant):
        return get_or_create_branding(tenant).social_urls

    def get_feature_flags(self, tenant):
        return {'videos': True, 'live_tv': True, 'search': True}


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['uuid', 'name', 'slug', 'description', 'show_in_menu', 'show_on_homepage']


class ArticleListSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source='author.display_name')
    category = serializers.CharField(source='category.name')

    class Meta:
        model = NewsArticle
        fields = ['uuid', 'title', 'slug', 'short_description', 'author', 'category', 'published_at', 'is_breaking', 'is_featured']


class ArticleDetailSerializer(ArticleListSerializer):
    tags = serializers.StringRelatedField(many=True)

    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + ['content', 'image_alt', 'tags', 'seo_title', 'meta_description']


class BreakingNewsSerializer(serializers.ModelSerializer):
    article_slug = serializers.CharField(source='article.slug')

    class Meta:
        model = BreakingNews
        fields = ['title', 'article_slug', 'ticker_order']


class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ['uuid', 'title', 'slug', 'description', 'source_type', 'video_url', 'duration', 'published_at', 'seo_title', 'meta_description']


class LiveTVSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiveTVChannel
        fields = ['uuid', 'name', 'slug', 'description', 'source_type', 'stream_url']


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ['uuid', 'title', 'slug', 'page_type', 'content', 'seo_title', 'meta_description']
