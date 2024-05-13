# Generated by Django 4.2.7 on 2024-05-13 14:18

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AutoRechargeSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_provider', models.IntegerField(choices=[(1, 'Stripe'), (2, 'Paypal')])),
                ('external_id', models.CharField(help_text='Subscription ID for PayPal and payment_method_id for Stripe', max_length=255)),
                ('topup_amount', models.IntegerField(blank=True, null=True)),
                ('topup_threshold', models.IntegerField(blank=True, null=True)),
            ],
        ),
    ]
