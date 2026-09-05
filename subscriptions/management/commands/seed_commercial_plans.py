from django.core.management.base import BaseCommand

from subscriptions.models import AddOn, Feature, Plan, PlanFeature, PlanPrice


FEATURES = [
    ('news_articles', 'News Articles', 'content', Feature.FeatureType.LIMIT, 'articles'),
    ('blog', 'Blog', 'content', Feature.FeatureType.BOOLEAN, ''),
    ('breaking_news', 'Breaking News', 'content', Feature.FeatureType.BOOLEAN, ''),
    ('custom_domain', 'Custom Domain', 'site', Feature.FeatureType.BOOLEAN, ''),
    ('epaper', 'ePaper', 'publishing', Feature.FeatureType.BOOLEAN, ''),
    ('epaper_editions_per_month', 'E-Papers Per Month', 'publishing', Feature.FeatureType.LIMIT, 'editions'),
    ('youtube_videos', 'YouTube Videos', 'video', Feature.FeatureType.BOOLEAN, ''),
    ('youtube_shorts', 'YouTube Shorts', 'video', Feature.FeatureType.BOOLEAN, ''),
    ('live_tv', 'Live TV', 'video', Feature.FeatureType.BOOLEAN, ''),
    ('adsense', 'AdSense', 'monetization', Feature.FeatureType.BOOLEAN, ''),
    ('advertisement_manager', 'Advertisement Manager', 'monetization', Feature.FeatureType.BOOLEAN, ''),
    ('advanced_seo', 'Advanced SEO', 'growth', Feature.FeatureType.BOOLEAN, ''),
    ('analytics', 'Analytics', 'growth', Feature.FeatureType.BOOLEAN, ''),
    ('multiple_staff', 'Multiple Staff', 'team', Feature.FeatureType.LIMIT, 'users'),
    ('mobile_app', 'Mobile App', 'distribution', Feature.FeatureType.BOOLEAN, ''),
    ('photo_gallery', 'Photo Gallery', 'media', Feature.FeatureType.BOOLEAN, ''),
    ('api_access', 'API Access', 'integration', Feature.FeatureType.BOOLEAN, ''),
    ('homepage_builder', 'Homepage Builder', 'site', Feature.FeatureType.BOOLEAN, ''),
    ('premium_themes', 'Premium Themes', 'site', Feature.FeatureType.BOOLEAN, ''),
]

PLAN_DEFAULTS = {
    Plan.Code.NEWS_STARTER: {
        'name': 'News Starter',
        'monthly_price': 39900,
        'yearly_price': 499000,
        'features': {
            'news_articles': (True, 150),
            'custom_domain': (True, None),
        },
    },
    Plan.Code.NEWS_VIDEO: {
        'name': 'News Basic',
        'monthly_price': 99900,
        'yearly_price': 999000,
        'features': {
            'news_articles': (True, 300),
            'blog': (True, None),
            'custom_domain': (True, None),
        },
    },
    Plan.Code.NEWS_PRO: {
        'name': 'News Pro',
        'monthly_price': 199900,
        'yearly_price': 1999000,
        'features': {
            'news_articles': (True, 1500),
            'blog': (True, None),
            'custom_domain': (True, None),
            'youtube_videos': (True, None),
            'youtube_shorts': (True, None),
        },
    },
    Plan.Code.PROFESSIONAL: {
        'name': 'News Professional',
        'monthly_price': 499900,
        'yearly_price': 4999000,
        'features': {
            'news_articles': (True, 10000),
            'blog': (True, None),
            'custom_domain': (True, None),
            'epaper': (True, None),
            'epaper_editions_per_month': (True, 30),
            'youtube_videos': (True, None),
            'youtube_shorts': (True, None),
        },
    },
}

ADD_ON_DEFAULTS = [
    ('epaper-addon', 'E-Paper Add-on', 'epaper', 49900, 499000, None),
    ('mobile-app-addon', 'Mobile App Add-on', 'mobile_app', 299900, 2999000, None),
    ('extra-staff-addon', 'Extra Staff', 'multiple_staff', 19900, 199000, 5),
]

DEPRECATED_PLAN_CODES = (Plan.Code.NEWS_BUSINESS,)


class Command(BaseCommand):
    help = 'Seed the commercial feature catalog and default SaaS plan entitlements.'

    def handle(self, *args, **options):
        features_by_code = {}
        for order, (code, name, category, feature_type, unit) in enumerate(FEATURES, start=10):
            feature, _ = Feature.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'category': category,
                    'feature_type': feature_type,
                    'default_unit': unit,
                    'is_active': True,
                    'is_public': True,
                    'display_order': order,
                },
            )
            features_by_code[code] = feature

        for code, plan_data in PLAN_DEFAULTS.items():
            plan, _ = Plan.objects.update_or_create(
                code=code,
                version=1,
                defaults={
                    'name': plan_data['name'],
                    'is_active': True,
                    'is_current_version': True,
                },
            )
            PlanPrice.objects.update_or_create(
                plan=plan,
                billing_cycle=PlanPrice.BillingCycle.MONTHLY,
                defaults={'amount': plan_data['monthly_price'], 'currency': 'INR', 'is_active': True},
            )
            PlanPrice.objects.update_or_create(
                plan=plan,
                billing_cycle=PlanPrice.BillingCycle.YEARLY,
                defaults={'amount': plan_data['yearly_price'], 'currency': 'INR', 'is_active': True},
            )
            PlanFeature.objects.filter(plan=plan).exclude(feature__code__in=plan_data['features'].keys()).update(
                is_enabled=False,
                limit_value=None,
            )
            for feature_code, (is_enabled, limit_value) in plan_data['features'].items():
                PlanFeature.objects.update_or_create(
                    plan=plan,
                    feature=features_by_code[feature_code],
                    defaults={
                        'is_enabled': is_enabled,
                        'limit_value': limit_value,
                    },
                )

        Plan.objects.filter(code__in=DEPRECATED_PLAN_CODES, version=1).update(
            is_active=False,
            is_current_version=False,
        )

        for order, (code, name, feature_code, monthly_price, yearly_price, limit_value) in enumerate(ADD_ON_DEFAULTS, start=10):
            AddOn.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'feature': features_by_code[feature_code],
                    'monthly_price': monthly_price,
                    'yearly_price': yearly_price,
                    'currency': 'INR',
                    'limit_value': limit_value,
                    'is_active': True,
                    'display_order': order,
                },
            )

        self.stdout.write(self.style.SUCCESS('Commercial feature catalog and plans seeded.'))
