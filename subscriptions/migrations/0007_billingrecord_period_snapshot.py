from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0006_subscription_offer_pricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='billingrecord',
            name='period_start',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='billingrecord',
            name='period_end',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
