# Generated by Django 4.2.7 on 2024-05-28 16:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0015_appuser_subscription_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='disable_rate_limits',
            field=models.BooleanField(default=False),
        ),
    ]
