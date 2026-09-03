from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase

from subscriptions.models import CustomerAcquisition, Plan, PlanPrice


class IdentifierLoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='geeta_2152',
            email='geeta@example.com',
            password='strongpass123',
        )
        plan = Plan.objects.create(name='News Starter', code='starter')
        price = PlanPrice.objects.create(plan=plan, amount=100, billing_cycle=PlanPrice.BillingCycle.MONTHLY)
        CustomerAcquisition.objects.create(
            user=self.user,
            plan_price=price,
            business_name='Geeta News',
            publication_name='Geeta',
            publication_slug='geeta',
            email='geeta@example.com',
            mobile='8279402152',
        )

    def test_login_with_email(self):
        user = authenticate(username='geeta@example.com', password='strongpass123')
        self.assertEqual(user, self.user)

    def test_login_with_mobile(self):
        user = authenticate(username='8279402152', password='strongpass123')
        self.assertEqual(user, self.user)

    def test_login_with_username(self):
        user = authenticate(username='geeta_2152', password='strongpass123')
        self.assertEqual(user, self.user)
