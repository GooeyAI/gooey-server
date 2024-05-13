# Generated by Django 4.2.7 on 2024-05-13 14:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
        ('app_users', '0015_appuser_monthly_spending_budget_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='auto_recharge_subscription',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='user', to='payments.autorechargesubscription'),
        ),
    ]
