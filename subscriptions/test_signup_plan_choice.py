from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from .forms import CustomerSignupForm, CustomerWorkspaceForm
from .models import Plan, PlanPrice


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SignupPlanChoiceTests(TestCase):
    def setUp(self):
        self.starter = Plan.objects.create(name='News Starter', code='news_starter')
        self.pro = Plan.objects.create(name='News Pro', code='news_pro')
        self.price = PlanPrice.objects.create(plan=self.starter, billing_cycle='monthly', amount=79800)
        self.pro_price = PlanPrice.objects.create(plan=self.pro, billing_cycle='monthly', amount=159800)
        self.user = get_user_model().objects.create_user(username='plan-owner')

    def data(self, price):
        return {'business_name': 'New publication', 'publication_name': 'New publication',
                'mobile': '9876543210', 'password': 'password123', 'confirm_password': 'password123',
                'price_id': str(price.pk), 'billing_months': '12', 'accepted_purchase_terms': 'on'}

    def test_changed_posted_plan_wins_over_initial_for_both_flows(self):
        for cls in [CustomerSignupForm, CustomerWorkspaceForm]:
            kwargs = {'user': self.user} if cls is CustomerWorkspaceForm else {}
            form = cls(self.data(self.pro_price), initial={'price_id': self.price.pk}, **kwargs)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data['price_id'], self.pro_price)
            self.assertEqual(form.cleaned_data['billing_months'], 12)
            self.assertEqual(form.selected_quote['name'], 'News Pro')
            self.assertEqual(form.selected_quote['payable'], '₹ 9,588')

    def test_inactive_and_old_plan_prices_rejected(self):
        self.pro.is_current_version = False
        self.pro.save()
        form = CustomerSignupForm(self.data(self.pro_price))
        self.assertFalse(form.is_valid())
        self.assertIn('price_id', form.errors)
        self.assertNotIn(str(self.pro_price.pk), form.signup_prices)
        self.price.is_active = False
        self.price.save()
        self.assertIn('price_id', CustomerSignupForm(self.data(self.price)).errors)

    def test_monthly_price_preferred_without_duplicate_plan_options(self):
        yearly = PlanPrice.objects.create(plan=self.starter, billing_cycle='yearly', amount=900000)
        form = CustomerSignupForm()
        self.assertIn(str(self.price.pk), form.signup_prices)
        self.assertNotIn(str(yearly.pk), form.signup_prices)

    def test_signup_renders_selection_quote_and_preserves_other_posted_fields(self):
        response = self.client.get('/saas/signup/', {'price': self.price.pk, 'months': 1})
        self.assertContains(response, '<select name="price_id"')
        self.assertContains(response, 'News Starter')
        self.assertContains(response, '₹ 399')
        self.assertContains(response, 'signup-plan-quotes')
        data = self.data(self.pro_price)
        data['confirm_password'] = 'different'
        response = self.client.post('/saas/signup/?price=' + str(self.price.pk), data)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form['business_name'].value(), 'New publication')
        self.assertEqual(form['price_id'].value(), str(self.pro_price.pk))
        self.assertEqual(form.selected_quote['name'], 'News Pro')
