from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from tenants.models import Tenant

from .models import AdCampaign, AdCreative, AdPlacement


class AdvertisementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(username='a')
        self.user_b = User.objects.create_user(username='b')
        self.tenant_a = Tenant.objects.create(owner=self.user_a, business_name='A', publication_name='A', slug='a', email='a@example.com')
        self.tenant_b = Tenant.objects.create(owner=self.user_b, business_name='B', publication_name='B', slug='b', email='b@example.com')
        self.campaign_a = AdCampaign.objects.create(tenant=self.tenant_a, name='A Campaign')
        self.placement_b = AdPlacement.objects.create(tenant=self.tenant_b, name='B Top', position=AdPlacement.Position.HOMEPAGE_TOP)

    def test_ad_creative_rejects_cross_tenant_placement_and_unsafe_url(self):
        creative = AdCreative(
            tenant=self.tenant_a,
            campaign=self.campaign_a,
            placement=self.placement_b,
            title='Bad',
            image='ads/bad.jpg',
            destination_url='javascript:alert(1)',
        )
        with self.assertRaises(ValidationError):
            creative.full_clean()
