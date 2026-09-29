from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gst', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='gstsettings',
            name='price_tax_mode',
            field=models.CharField(
                choices=[
                    ('exclusive', 'GST extra on checkout'),
                    ('inclusive', 'GST included in discounted price'),
                ],
                default='exclusive',
                max_length=20,
            ),
        ),
    ]
