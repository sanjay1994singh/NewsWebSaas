from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0016_update_news_article_monthly_limits'),
    ]

    operations = [
        migrations.AddField(model_name='billingrecord', name='tax_amount', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='billingrecord', name='tax_rate_percent', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='billingrecord', name='taxable_amount', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='customeracquisition', name='tax_amount', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='customeracquisition', name='tax_rate_percent', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='customeracquisition', name='taxable_amount', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='planchangerequest', name='tax_amount', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='planchangerequest', name='tax_rate_percent', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='planchangerequest', name='taxable_amount', field=models.PositiveIntegerField(default=0)),
    ]