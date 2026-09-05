import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from news.models import AuthorProfile, NewsArticle
from tenants.models import Tenant, TenantMembership
from themes.models import TenantBranding, ThemeActivation

from .builder import (
    add_homepage_block,
    get_or_create_layout,
    publish_homepage_layout,
    restore_default_layout,
    restore_published_to_draft,
    update_homepage_blocks,
)
from .models import FooterSection, HomepageBlock, HomepageLayout, Menu, MenuItem, Page


@override_settings(ALLOWED_HOSTS=['testserver', 'a.example.com'])
class WebsiteBuilderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(username='owner-a', password='testpass123')
        self.user_b = User.objects.create_user(username='owner-b', password='testpass123')
        self.tenant_a = Tenant.objects.create(
            owner=self.user_a,
            business_name='A Media',
            publication_name='A News',
            slug='a-news',
            email='a@example.com',
            status=Tenant.Status.ACTIVE,
        )
        self.tenant_b = Tenant.objects.create(
            owner=self.user_b,
            business_name='B Media',
            publication_name='B News',
            slug='b-news',
            email='b@example.com',
            status=Tenant.Status.ACTIVE,
        )
        TenantMembership.objects.create(tenant=self.tenant_a, user=self.user_a, role=TenantMembership.Role.OWNER, status=TenantMembership.Status.ACTIVE, joined_at=timezone.now())
        TenantMembership.objects.create(tenant=self.tenant_b, user=self.user_b, role=TenantMembership.Role.OWNER, status=TenantMembership.Status.ACTIVE, joined_at=timezone.now())
        self.category_a = Category.objects.create(tenant=self.tenant_a, name='Politics', slug='politics')
        self.category_b = Category.objects.create(tenant=self.tenant_b, name='Sports', slug='sports')
        self.author_a = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='Reporter A', slug='reporter-a')
        self.article_a = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=self.category_a,
            author=self.author_a,
            title='Builder Article',
            slug='builder-article',
            content='body',
            status=NewsArticle.Status.PUBLISHED,
        )

    def test_default_draft_layout_is_created_with_blocks(self):
        layout = get_or_create_layout(self.tenant_a)
        self.assertEqual(layout.status, HomepageLayout.Status.DRAFT)
        self.assertGreaterEqual(layout.blocks.count(), 6)

    def test_builder_rejects_foreign_category_ids(self):
        layout = get_or_create_layout(self.tenant_a)
        block = layout.blocks.first()
        with self.assertRaises(PermissionDenied):
            update_homepage_blocks(
                tenant=self.tenant_a,
                layout=layout,
                payload=[{'id': block.id, 'category_id': self.category_b.id, 'heading': 'Attack'}],
            )

    def test_category_news_block_requires_same_tenant_category(self):
        layout = get_or_create_layout(self.tenant_a)
        block = add_homepage_block(
            tenant=self.tenant_a,
            layout=layout,
            block_type=HomepageBlock.BlockType.CATEGORY_NEWS,
            category_id=self.category_a.id,
        )
        self.assertEqual(block.category, self.category_a)
        with self.assertRaises(PermissionDenied):
            add_homepage_block(
                tenant=self.tenant_a,
                layout=layout,
                block_type=HomepageBlock.BlockType.CATEGORY_NEWS,
                category_id=self.category_b.id,
            )

    def test_draft_publish_restore_flow_keeps_live_layout_stable(self):
        draft = get_or_create_layout(self.tenant_a)
        first = draft.blocks.first()
        first.heading = 'Draft Only'
        first.save()
        published = publish_homepage_layout(self.tenant_a)
        self.assertEqual(published.blocks.order_by('order').first().heading, 'Draft Only')
        first.heading = 'Changed Draft'
        first.save()
        published.refresh_from_db()
        self.assertEqual(published.blocks.order_by('order').first().heading, 'Draft Only')
        restore_published_to_draft(self.tenant_a)
        draft.refresh_from_db()
        self.assertEqual(draft.blocks.order_by('order').first().heading, 'Draft Only')
        restore_default_layout(self.tenant_a)
        self.assertNotEqual(draft.blocks.order_by('order').first().heading, 'Draft Only')

    def test_custom_content_block_is_sanitized(self):
        layout = get_or_create_layout(self.tenant_a)
        block = HomepageBlock.objects.create(
            tenant=self.tenant_a,
            layout=layout,
            block_type=HomepageBlock.BlockType.CUSTOM_CONTENT,
            heading='Custom',
            settings={'content': '<p>Hello</p><script>alert(1)</script>'},
        )
        block.refresh_from_db()
        self.assertNotIn('<script', block.settings['content'])
        self.assertIn('<p>Hello</p>', block.settings['content'])

    def test_menu_item_rejects_cross_tenant_page(self):
        menu = Menu.objects.create(tenant=self.tenant_a, name='Header', location=Menu.Location.HEADER)
        page_b = Page.objects.create(tenant=self.tenant_b, title='About', slug='about', content='B')
        item = MenuItem(
            tenant=self.tenant_a,
            menu=menu,
            label='About',
            link_type=MenuItem.LinkType.PAGE,
            page=page_b,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_footer_sections_are_tenant_scoped(self):
        FooterSection.objects.create(tenant=self.tenant_a, title='A Footer', order=1)
        FooterSection.objects.create(tenant=self.tenant_b, title='B Footer', order=1)
        self.assertEqual(list(FooterSection.objects.for_tenant(self.tenant_a).values_list('title', flat=True)), ['A Footer'])

    def test_theme_activation_and_branding_are_tenant_specific(self):
        ThemeActivation.objects.create(tenant=self.tenant_a, active_theme=ThemeActivation.ThemeKey.TV)
        TenantBranding.objects.create(tenant=self.tenant_a, publication_name='A Brand')
        self.assertEqual(ThemeActivation.objects.for_tenant(self.tenant_a).get().active_theme, ThemeActivation.ThemeKey.TV)
        self.assertEqual(TenantBranding.objects.for_tenant(self.tenant_b).count(), 0)

    def test_save_builder_endpoint_reorders_blocks_for_active_tenant(self):
        from domains.models import TenantDomain

        TenantDomain.objects.create(tenant=self.tenant_a, domain='a.example.com', domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN, is_verified=True)
        layout = get_or_create_layout(self.tenant_a)
        blocks = list(layout.blocks.order_by('order')[:2])
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse('pages:save_homepage_draft'),
            data=json.dumps([
                {'id': blocks[1].id, 'heading': 'Second First', 'is_enabled': True},
                {'id': blocks[0].id, 'heading': 'First Second', 'is_enabled': True},
            ]),
            content_type='application/json',
            HTTP_HOST='a.example.com',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(layout.blocks.order_by('order').values_list('heading', flat=True)[:2]), ['Second First', 'First Second'])

    def test_owner_can_manage_only_required_static_pages(self):
        self.client.force_login(self.user_a)

        response = self.client.get(reverse('pages:tenant_static_page_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Privacy Policy')
        self.assertContains(response, 'Editorial Policy')
        self.assertEqual(Page.objects.filter(tenant=self.tenant_a, is_published=True).count(), 9)

        page = Page.objects.get(tenant=self.tenant_a, slug='privacy-policy')
        edit_response = self.client.post(
            reverse('pages:tenant_static_page_edit', args=[page.id]),
            {
                'title': 'Privacy Policy',
                'content': '<p>Updated tenant privacy content.</p><script>alert(1)</script>',
                'seo_title': 'Privacy - A News',
                'meta_description': 'Updated privacy policy.',
            },
        )

        self.assertEqual(edit_response.status_code, 302)
        page.refresh_from_db()
        self.assertIn('Updated tenant privacy content', page.content)
        self.assertNotIn('<script', page.content)

    def test_owner_cannot_edit_other_tenant_static_page(self):
        from subscriptions.services import ensure_required_tenant_pages

        ensure_required_tenant_pages(tenant=self.tenant_b)
        foreign_page = Page.objects.get(tenant=self.tenant_b, slug='privacy-policy')
        self.client.force_login(self.user_a)

        response = self.client.get(reverse('pages:tenant_static_page_edit', args=[foreign_page.id]))

        self.assertEqual(response.status_code, 404)
