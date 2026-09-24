from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0004_tenantadvertisement'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='article_view_tracking_enabled',
            field=models.BooleanField(default=True),
        ),
    ]