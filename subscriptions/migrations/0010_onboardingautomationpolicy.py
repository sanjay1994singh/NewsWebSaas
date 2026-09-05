from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0009_alter_planchangerequest_provider_payload'),
    ]

    operations = [
        migrations.CreateModel(
            name='OnboardingAutomationPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(default='Default onboarding policy', max_length=80)),
                ('mode', models.CharField(choices=[('manual', 'Manual review'), ('instant', 'Auto approve and publish instantly'), ('delayed', 'Auto approve and publish after delay')], default='instant', max_length=20)),
                ('delay_minutes', models.PositiveIntegerField(default=30)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
            ],
            options={
                'verbose_name': 'Onboarding automation policy',
                'verbose_name_plural': 'Onboarding automation policy',
            },
        ),
    ]
