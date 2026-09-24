from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0005_tenant_article_view_tracking_enabled'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenantadvertisement',
            name='placement',
            field=models.CharField(
                choices=[
                    ('header_rectangle', 'Header rectangle - 970 x 250 recommended'),
                    ('after_hero_rectangle', 'After top story - 970 x 250 recommended'),
                    ('sidebar_square', 'Sidebar ad - original size'),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
    ]