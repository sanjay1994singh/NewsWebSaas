from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from tenants.models import Tenant

from .models import MediaAsset, PhotoGallery, PhotoGalleryItem


class GalleryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(username='a')
        self.user_b = User.objects.create_user(username='b')
        self.tenant_a = Tenant.objects.create(owner=self.user_a, business_name='A', publication_name='A', slug='a', email='a@example.com')
        self.tenant_b = Tenant.objects.create(owner=self.user_b, business_name='B', publication_name='B', slug='b', email='b@example.com')

    def test_gallery_item_rejects_cross_tenant_media(self):
        gallery = PhotoGallery.objects.create(tenant=self.tenant_a, title='A Gallery', slug='a-gallery')
        media = MediaAsset.objects.create(tenant=self.tenant_b, filename='b.jpg', file='media_library/b.jpg')
        item = PhotoGalleryItem(tenant=self.tenant_a, gallery=gallery, media=media)
        with self.assertRaises(ValidationError):
            item.full_clean()
