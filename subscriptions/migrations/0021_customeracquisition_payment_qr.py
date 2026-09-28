from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0020_customeracquisition_payment_link'),
    ]

    operations = [
        migrations.AddField(
            model_name='customeracquisition',
            name='provider_payment_qr_id',
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name='customeracquisition',
            name='provider_payment_qr_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='customeracquisition',
            name='provider_payment_qr_image_url',
            field=models.URLField(blank=True),
        ),
    ]
