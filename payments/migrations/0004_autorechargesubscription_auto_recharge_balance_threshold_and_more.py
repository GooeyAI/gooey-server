# Generated by Django 4.2.7 on 2024-05-22 21:17

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_alter_subscription_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='autorechargesubscription',
            name='auto_recharge_balance_threshold',
            field=models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name='autorechargesubscription',
            name='auto_recharge_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='autorechargesubscription',
            name='auto_recharge_topup_amount',
            field=models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name='autorechargesubscription',
            name='external_id',
            field=models.CharField(blank=True, help_text='Subscription ID for PayPal', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='autorechargesubscription',
            name='payment_provider',
            field=models.IntegerField(blank=True, choices=[(1, 'Stripe'), (2, 'PayPal')], null=True),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='external_id',
            field=models.CharField(help_text='Subscription ID from the payment provider', max_length=255),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='payment_provider',
            field=models.IntegerField(choices=[(1, 'Stripe'), (2, 'PayPal')]),
        ),
    ]
