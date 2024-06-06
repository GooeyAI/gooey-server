# Generated by Django 4.2.7 on 2024-05-27 05:48

from django.db import migrations, models
import payments.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.IntegerField(choices=[(1, 'BASIC'), (2, 'PREMIUM'), (3, 'STARTER'), (4, 'CREATOR'), (5, 'BUSINESS'), (6, 'ENTERPRISE')])),
                ('payment_provider', models.IntegerField(choices=[(1, 'Stripe'), (2, 'PayPal')])),
                ('external_id', models.CharField(help_text='Subscription ID from the payment provider', max_length=255)),
                ('auto_recharge_enabled', models.BooleanField(default=True)),
                ('auto_recharge_balance_threshold', models.IntegerField()),
                ('auto_recharge_topup_amount', models.IntegerField(default=10)),
                ('monthly_spending_budget', models.IntegerField(blank=True, help_text='In USD, pause auto-recharge just before the spending exceeds this amount in a calendar month', null=True)),
                ('monthly_spending_notification_threshold', models.IntegerField(blank=True, help_text='In USD, send an email when spending crosses this threshold in a calendar month', null=True)),
                ('monthly_spending_notification_sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [models.Index(fields=['plan'], name='payments_su_plan_23b2f6_idx')],
                'unique_together': {('payment_provider', 'external_id')},
            },
        ),
    ]
