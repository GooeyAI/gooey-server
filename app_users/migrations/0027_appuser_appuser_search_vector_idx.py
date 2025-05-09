# Generated by Django 5.1.3 on 2025-04-21 05:12

import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0026_alter_appusertransaction_plan'),
        ('payments', '0006_alter_subscription_plan'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='appuser',
            index=django.contrib.postgres.indexes.GinIndex(django.contrib.postgres.search.SearchVector('display_name', config='english'), name='appuser_search_vector_idx'),
        ),
    ]
