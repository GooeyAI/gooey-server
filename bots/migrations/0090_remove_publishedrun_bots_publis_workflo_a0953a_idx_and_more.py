# Generated by Django 5.1.2 on 2024-11-28 21:25

import bots.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0023_alter_appusertransaction_workspace'),
        ('bots', '0089_remove_publishedrun_bots_publis_workflo_d3ad4e_idx_and_more'),
        ('workspaces', '0005_alter_workspaceinvite_status'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='publishedrun',
            name='bots_publis_workflo_a0953a_idx',
        ),
        migrations.RemoveIndex(
            model_name='publishedrun',
            name='bots_publis_workflo_36a83a_idx',
        ),
        migrations.RemoveIndex(
            model_name='publishedrun',
            name='bots_publis_workflo_ca43bd_idx',
        ),
        migrations.AlterField(
            model_name='publishedrun',
            name='workspace',
            field=models.ForeignKey(default=bots.models.get_default_published_run_workspace, on_delete=django.db.models.deletion.CASCADE, to='workspaces.workspace'),
        ),
        migrations.AddIndex(
            model_name='publishedrun',
            index=models.Index(fields=['is_approved_example', 'visibility', 'published_run_id', 'updated_at', 'workflow', 'example_priority'], name='bots_publis_is_appr_a989ec_idx'),
        ),
    ]