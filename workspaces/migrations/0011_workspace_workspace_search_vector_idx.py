# Generated by Django 5.1.3 on 2025-04-21 05:12

import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0027_appuser_appuser_search_vector_idx'),
        ('handles', '0002_remove_handle_handle_upper_name_is_unique_and_more'),
        ('payments', '0006_alter_subscription_plan'),
        ('workspaces', '0010_workspace_banner_url'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='workspace',
            index=django.contrib.postgres.indexes.GinIndex(django.contrib.postgres.search.SearchVector('name', config='english'), name='workspace_search_vector_idx'),
        ),
    ]
