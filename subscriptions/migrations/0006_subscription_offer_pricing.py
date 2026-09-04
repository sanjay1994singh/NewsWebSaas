from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0005_store_razorpay_checkout_references"),
    ]

    operations = [
        migrations.AddField(
            model_name="customeracquisition",
            name="billing_months",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="customeracquisition",
            name="list_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="customeracquisition",
            name="discount_percent",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="customeracquisition",
            name="discount_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="customeracquisition",
            name="payable_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tenantsubscription",
            name="billing_months",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="billingrecord",
            name="billing_months",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="billingrecord",
            name="list_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="billingrecord",
            name="discount_percent",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="billingrecord",
            name="discount_amount",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
