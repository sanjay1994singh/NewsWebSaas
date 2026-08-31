from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from categories.models import Category
from domains.models import TenantDomain
from news.models import AuthorProfile, NewsArticle
from pages.builder import add_homepage_block, get_or_create_layout, publish_homepage_layout, restore_default_layout
from pages.models import HomepageBlock, Menu, MenuItem
from tenants.models import Tenant, TenantMembership
from themes.models import TenantBranding, ThemeActivation


class Command(BaseCommand):
    help = "Create isolated demo tenants for final multi-tenant verification."

    def handle(self, *args, **options):
        User = get_user_model()
        demos = [
            ('mathura-owner', 'Mathura News', 'mathura-news', 'mathura.example.com', ThemeActivation.ThemeKey.CLASSIC, ['Mathura', 'Vrindavan', 'Politics']),
            ('bharat-owner', 'Bharat Live', 'bharat-live', 'bharat.example.com', ThemeActivation.ThemeKey.MODERN, ['National', 'Business', 'Sports']),
        ]
        for username, publication, slug, domain_name, theme, categories in demos:
            user, _ = User.objects.get_or_create(username=username, defaults={'email': f'{username}@example.com'})
            tenant, _ = Tenant.objects.get_or_create(
                slug=slug,
                defaults={'owner': user, 'business_name': publication, 'publication_name': publication, 'email': user.email, 'status': Tenant.Status.ACTIVE},
            )
            TenantMembership.objects.get_or_create(tenant=tenant, user=user, defaults={'role': TenantMembership.Role.OWNER, 'status': TenantMembership.Status.ACTIVE, 'joined_at': timezone.now()})
            TenantDomain.objects.get_or_create(tenant=tenant, domain=domain_name, defaults={'domain_type': TenantDomain.DomainType.CUSTOM_DOMAIN, 'is_verified': True, 'is_primary': True, 'status': TenantDomain.Status.ACTIVE})
            TenantBranding.objects.get_or_create(tenant=tenant, defaults={'publication_name': publication})
            ThemeActivation.objects.get_or_create(tenant=tenant, defaults={'active_theme': theme, 'draft_theme': theme})
            author, _ = AuthorProfile.objects.get_or_create(tenant=tenant, slug='editor', defaults={'display_name': f'{publication} Editor'})
            menu, _ = Menu.objects.get_or_create(tenant=tenant, location=Menu.Location.HEADER, defaults={'name': 'Header'})
            layout = restore_default_layout(tenant)
            for order, name in enumerate(categories, start=1):
                category, _ = Category.objects.get_or_create(tenant=tenant, slug=name.lower().replace(' ', '-'), defaults={'name': name, 'show_in_menu': True})
                MenuItem.objects.get_or_create(tenant=tenant, menu=menu, label=name, link_type=MenuItem.LinkType.CATEGORY, category=category, defaults={'order': order})
                NewsArticle.objects.get_or_create(tenant=tenant, slug=f'{category.slug}-demo', defaults={'category': category, 'author': author, 'title': f'{name} Demo Story', 'content': 'Demo content', 'status': NewsArticle.Status.PUBLISHED})
            publish_homepage_layout(tenant)
            self.stdout.write(self.style.SUCCESS(f"Demo tenant ready: {publication}"))
