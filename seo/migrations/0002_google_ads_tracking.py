from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('seo', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantseosettings',
            name='google_ads_conversion_label',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='tenantseosettings',
            name='google_ads_id',
            field=models.CharField(blank=True, max_length=40),
        ),
    ]