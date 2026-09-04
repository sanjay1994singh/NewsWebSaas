from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from media_library.models import MediaAsset
from pages.models import Page
from tenants.models import Tenant, TenantMembership

from .forms import NewsArticleForm
from .models import AuthorProfile, BreakingNews, NewsArticle, Tag
from .services import active_breaking_news_for_tenant, search_articles


def tiny_gif(name='article.gif'):
    return SimpleUploadedFile(
        name,
        b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',
        content_type='image/gif',
    )


@override_settings(ALLOWED_HOSTS=['testserver', 'a.example.com', 'b.example.com'])
class TenantNewsCMSTests(TestCase):
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
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=TenantMembership.Role.OWNER,
            status=TenantMembership.Status.ACTIVE,
            joined_at=timezone.now(),
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role=TenantMembership.Role.OWNER,
            status=TenantMembership.Status.ACTIVE,
            joined_at=timezone.now(),
        )
        self.category_a = Category.objects.create(tenant=self.tenant_a, name='Politics', slug='politics')
        self.category_b = Category.objects.create(tenant=self.tenant_b, name='Politics', slug='politics')
        self.author_a = AuthorProfile.objects.create(tenant=self.tenant_a, display_name='Reporter A', slug='reporter')
        self.author_b = AuthorProfile.objects.create(tenant=self.tenant_b, display_name='Reporter B', slug='reporter')
        self.tag_a = Tag.objects.create(tenant=self.tenant_a, name='Election', slug='election')
        self.tag_b = Tag.objects.create(tenant=self.tenant_b, name='Election', slug='election')
        self.article_a = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=self.category_a,
            author=self.author_a,
            title='Shared headline',
            slug='shared',
            short_description='A tenant story',
            content='<p>Safe</p><script>alert(1)</script>',
            status=NewsArticle.Status.PUBLISHED,
        )
        self.article_b = NewsArticle.objects.create(
            tenant=self.tenant_b,
            category=self.category_b,
            author=self.author_b,
            title='Secret competitor headline',
            slug='shared',
            short_description='B tenant story',
            content='<p>Private</p>',
            status=NewsArticle.Status.PUBLISHED,
        )

    def test_category_slug_uniqueness_is_per_tenant(self):
        self.assertEqual(Category.objects.filter(slug='politics').count(), 2)
        with self.assertRaises(IntegrityError):
            Category.objects.create(tenant=self.tenant_a, name='Politics Duplicate', slug='politics')

    def test_article_slug_uniqueness_is_per_tenant(self):
        self.assertEqual(NewsArticle.objects.filter(slug='shared').count(), 2)
        with self.assertRaises(IntegrityError):
            NewsArticle.objects.create(
                tenant=self.tenant_a,
                category=self.category_a,
                author=self.author_a,
                title='Duplicate',
                slug='shared',
                content='duplicate',
            )

    def test_cms_root_opens_article_dashboard(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('news:article_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'News Publishing')
        self.assertContains(response, 'Shared headline')
        self.assertContains(response, 'Add News')
        self.assertContains(response, 'Edit')
        self.assertContains(response, 'Delete')

    def test_owner_can_create_update_and_delete_article_from_cms(self):
        self.client.force_login(self.user_a)

        create_response = self.client.post(
            reverse('news:article_create'),
            {
                'category': self.category_a.pk,
                'author': self.author_a.pk,
                'title': 'Fresh city update',
                'slug': '',
                'content': '<p>Fresh body</p>',
                'city': 'Delhi',
                'state': 'Delhi',
                'featured_image': tiny_gif(),
                'status': NewsArticle.Status.DRAFT,
                'allow_comments': 'on',
                'robots_index': 'on',
                'robots_follow': 'on',
            },
        )

        self.assertRedirects(create_response, reverse('news:article_dashboard'))
        article = NewsArticle.objects.get(tenant=self.tenant_a, slug='fresh-city-update')
        self.assertEqual(article.title, 'Fresh city update')

        update_response = self.client.post(
            reverse('news:article_update', args=[article.uuid]),
            {
                'category': self.category_a.pk,
                'author': self.author_a.pk,
                'title': 'Fresh city update published',
                'slug': article.slug,
                'content': '<p>Fresh body updated</p>',
                'city': 'Delhi',
                'state': 'Delhi',
                'status': NewsArticle.Status.PUBLISHED,
                'allow_comments': 'on',
                'robots_index': 'on',
                'robots_follow': 'on',
            },
        )

        self.assertRedirects(update_response, reverse('news:article_dashboard'))
        article.refresh_from_db()
        self.assertEqual(article.title, 'Fresh city update published')
        self.assertEqual(article.status, NewsArticle.Status.PUBLISHED)
        self.assertIsNotNone(article.published_at)

        delete_response = self.client.post(reverse('news:article_delete', args=[article.uuid]))
        self.assertRedirects(delete_response, reverse('news:article_dashboard'))
        self.assertFalse(NewsArticle.objects.filter(pk=article.pk).exists())

    def test_article_form_uses_post_specific_publisher_name(self):
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse('news:article_create'),
            {
                'category': self.category_a.pk,
                'publisher_name': 'City Desk',
                'title': 'Byline update',
                'slug': '',
                'content': '<p>Body</p>',
                'city': 'Delhi',
                'state': 'Delhi',
                'featured_image': tiny_gif('publisher.gif'),
                'status': NewsArticle.Status.PUBLISHED,
                'allow_comments': 'on',
                'robots_index': 'on',
                'robots_follow': 'on',
            },
        )

        self.assertRedirects(response, reverse('news:article_dashboard'))
        article = NewsArticle.objects.get(tenant=self.tenant_a, slug='byline-update')
        self.assertEqual(article.public_publisher_name, 'City Desk')

    def test_default_editor_name_is_not_public_publisher_name(self):
        default_author = AuthorProfile.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            display_name=self.tenant_a.publication_name,
            slug='editor',
        )
        article = NewsArticle.objects.create(
            tenant=self.tenant_a,
            category=self.category_a,
            author=default_author,
            title='No public owner byline',
            slug='no-public-owner-byline',
            content='<p>Body</p>',
            status=NewsArticle.Status.PUBLISHED,
        )

        self.assertEqual(article.public_publisher_name, '')

    def test_article_detail_only_shows_selected_publisher_name(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('news:article_detail', args=[self.article_a.uuid]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reporter A')
        article_section = response.content.decode().split('<main class="page article-view">', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('owner-a', article_section)
        self.assertNotIn('A Media', article_section)

    def test_article_rejects_cross_tenant_category_and_author(self):
        article = NewsArticle(
            tenant=self.tenant_a,
            category=self.category_b,
            author=self.author_b,
            title='Bad boundaries',
            slug='bad-boundaries',
            content='x',
        )
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_article_form_rejects_foreign_category_author_and_tag(self):
        form = NewsArticleForm(
            data={
                'category': self.category_b.pk,
                'author': self.author_b.pk,
                'reporters': [self.author_b.pk],
                'tags': [self.tag_b.pk],
                'title': 'Form attack',
                'slug': 'form-attack',
                'content': 'body',
                'status': NewsArticle.Status.DRAFT,
                'allow_comments': 'on',
                'robots_index': 'on',
                'robots_follow': 'on',
            },
            tenant=self.tenant_a,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)
        self.assertIn('author', form.errors)
        self.assertIn('tags', form.errors)

    def test_category_list_is_tenant_scoped(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('news:category_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.category_a.name)
        self.assertContains(response, reverse('news:category_update', args=[self.category_a.pk]))
        self.assertNotContains(response, reverse('news:category_update', args=[self.category_b.pk]))

    def test_ckeditor_upload_is_saved_inside_current_tenant_folder(self):
        self.client.force_login(self.user_a)
        upload = tiny_gif('editor.gif')

        response = self.client.post(reverse('news:ckeditor_image_upload'), {'upload': upload})

        self.assertEqual(response.status_code, 200)
        url = response.json()['url']
        self.assertIn(f'/media/articles/editor/{self.tenant_a.id}/', url)
        self.assertNotIn(f'/media/articles/editor/{self.tenant_b.id}/', url)

    def test_article_update_shows_current_featured_image_preview(self):
        self.client.force_login(self.user_a)
        self.article_a.featured_image = 'articles/current.jpg'
        self.article_a.save(update_fields=['featured_image', 'updated_at'])

        response = self.client.get(reverse('news:article_update', args=[self.article_a.uuid]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current featured image')
        self.assertContains(response, 'src="/media/articles/current.jpg"')

    def test_search_never_returns_other_tenant_content(self):
        results = list(search_articles(tenant=self.tenant_a, query='competitor'))
        self.assertEqual(results, [])
        results = list(search_articles(tenant=self.tenant_b, query='competitor'))
        self.assertEqual(results, [self.article_b])

    def test_direct_article_url_blocks_cross_tenant_idor(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('news:article_detail', args=[self.article_b.uuid]))
        self.assertEqual(response.status_code, 403)

    def test_unsafe_html_is_sanitized(self):
        self.article_a.refresh_from_db()
        self.assertNotIn('<script', self.article_a.content)
        self.assertIn('<p>Safe</p>', self.article_a.content)

    def test_breaking_news_is_tenant_scoped(self):
        BreakingNews.objects.create(tenant=self.tenant_a, article=self.article_a, title='A breaking', ticker_order=1)
        BreakingNews.objects.create(tenant=self.tenant_b, article=self.article_b, title='B breaking', ticker_order=1)
        titles = [item.title for item in active_breaking_news_for_tenant(self.tenant_a)]
        self.assertEqual(titles, ['A breaking'])

    def test_media_library_is_tenant_scoped(self):
        MediaAsset.objects.create(tenant=self.tenant_a, filename='a.jpg', file='media_library/a.jpg')
        MediaAsset.objects.create(tenant=self.tenant_b, filename='b.jpg', file='media_library/b.jpg')
        self.assertEqual(list(MediaAsset.objects.for_tenant(self.tenant_a).values_list('filename', flat=True)), ['a.jpg'])

    def test_pages_are_tenant_scoped_and_sanitized(self):
        page = Page.objects.create(
            tenant=self.tenant_a,
            title='About Us',
            slug='about',
            page_type=Page.PageType.ABOUT,
            content='<h2>About</h2><iframe src="https://evil.example"></iframe>',
            is_published=True,
        )
        Page.objects.create(
            tenant=self.tenant_b,
            title='About Us',
            slug='about',
            page_type=Page.PageType.ABOUT,
            content='B about',
            is_published=True,
        )
        page.refresh_from_db()
        self.assertNotIn('<iframe', page.content)
        self.assertEqual(Page.objects.for_tenant(self.tenant_a).count(), 1)
