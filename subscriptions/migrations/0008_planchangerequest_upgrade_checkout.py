from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0007_billingrecord_period_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='planchangerequest',
            name='billing_months',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='credit_amount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='currency',
            field=models.CharField(default='INR', max_length=3),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='discount_amount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='discount_percent',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='list_amount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='payable_amount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='period_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='period_start',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='plan_price',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='plan_change_requests', to='subscriptions.planprice'),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='provider_order_id',
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='provider_payment_id',
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='provider_payload',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='planchangerequest',
            name='provider_signature',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
