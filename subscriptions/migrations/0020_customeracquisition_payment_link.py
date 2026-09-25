from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0019_tenantonboarding_header_banner'),
    ]

    operations = [
        migrations.AddField(
            model_name='customeracquisition',
            name='provider_payment_link_id',
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name='customeracquisition',
            name='provider_payment_link_url',
            field=models.URLField(blank=True),
        ),
    ]