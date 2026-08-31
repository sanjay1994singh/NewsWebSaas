from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from categories.models import Category
from livetv.models import LiveTVChannel
from news.models import NewsArticle
from news.services import active_breaking_news_for_tenant, published_articles_for_tenant, search_articles
from pages.builder import get_or_create_layout
from pages.models import HomepageLayout, Page
from tenants.models import Tenant
from videos.models import Video

from .serializers import (
    ArticleDetailSerializer,
    ArticleListSerializer,
    BreakingNewsSerializer,
    CategorySerializer,
    LiveTVSerializer,
    PageSerializer,
    SiteConfigSerializer,
    VideoSerializer,
)


def resolve_api_tenant(request):
    tenant = getattr(request, 'tenant', None)
    public_id = request.headers.get('X-Tenant-Public-ID') or request.query_params.get('tenant')
    if public_id:
        try:
            requested = Tenant.objects.get(uuid=public_id, status__in=[Tenant.Status.TRIAL, Tenant.Status.ACTIVE])
        except Tenant.DoesNotExist as exc:
            raise PermissionDenied("Unknown tenant.") from exc
        if tenant and tenant.id != requested.id:
            raise PermissionDenied("Tenant identifier does not match request host.")
        tenant = requested
    if tenant is None:
        raise PermissionDenied("Tenant could not be resolved.")
    return tenant


@method_decorator(cache_control(public=True, max_age=60), name='dispatch')
class SiteConfigView(APIView):
    def get(self, request):
        tenant = resolve_api_tenant(request)
        return Response(SiteConfigSerializer(tenant).data)


class HomepageView(APIView):
    def get(self, request):
        tenant = resolve_api_tenant(request)
        layout = get_or_create_layout(tenant, HomepageLayout.Status.PUBLISHED)
        return Response({'blocks': [{'type': block.block_type, 'heading': block.heading, 'order': block.order} for block in layout.blocks.filter(is_enabled=True)]})


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.objects.for_tenant(resolve_api_tenant(self.request)).filter(is_active=True)


class ArticleListView(generics.ListAPIView):
    serializer_class = ArticleListSerializer

    def get_queryset(self):
        return published_articles_for_tenant(resolve_api_tenant(self.request))


class ArticleDetailView(generics.RetrieveAPIView):
    serializer_class = ArticleDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return published_articles_for_tenant(resolve_api_tenant(self.request))


class BreakingNewsView(generics.ListAPIView):
    serializer_class = BreakingNewsSerializer

    def get_queryset(self):
        return active_breaking_news_for_tenant(resolve_api_tenant(self.request))


class SearchView(generics.ListAPIView):
    serializer_class = ArticleListSerializer

    def get_queryset(self):
        return search_articles(tenant=resolve_api_tenant(self.request), query=self.request.query_params.get('q'))


class VideoListView(generics.ListAPIView):
    serializer_class = VideoSerializer

    def get_queryset(self):
        return Video.objects.for_tenant(resolve_api_tenant(self.request)).filter(status=Video.Status.PUBLISHED)


class LiveTVListView(generics.ListAPIView):
    serializer_class = LiveTVSerializer

    def get_queryset(self):
        return LiveTVChannel.objects.for_tenant(resolve_api_tenant(self.request)).filter(is_active=True)


class PageListView(generics.ListAPIView):
    serializer_class = PageSerializer

    def get_queryset(self):
        return Page.objects.for_tenant(resolve_api_tenant(self.request)).filter(is_published=True)
