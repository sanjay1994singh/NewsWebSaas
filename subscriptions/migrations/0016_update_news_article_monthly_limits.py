from django.db import migrations


LIMITS_BY_PLAN_CODE = {
    'news_starter': 150,
    'news_video': 300,
    'news_pro': 1500,
    'professional': 10000,
}


def update_news_article_limits(apps, schema_editor):
    Feature = apps.get_model('subscriptions', 'Feature')
    Plan = apps.get_model('subscriptions', 'Plan')
    PlanFeature = apps.get_model('subscriptions', 'PlanFeature')
    try:
        feature = Feature.objects.get(code='news_articles')
    except Feature.DoesNotExist:
        return
    for plan_code, limit in LIMITS_BY_PLAN_CODE.items():
        plan_ids = Plan.objects.filter(code=plan_code).values_list('id', flat=True)
        PlanFeature.objects.filter(plan_id__in=plan_ids, feature=feature).update(
            is_enabled=True,
            limit_value=limit,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0015_billingrecord_entitlement_snapshot_and_more'),
    ]

    operations = [
        migrations.RunPython(update_news_article_limits, noop_reverse),
    ]
