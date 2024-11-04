# Generated by Django 5.1.2 on 2024-11-04 13:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0023_alter_appusertransaction_workspace'),
        ('bots', '0084_remove_botintegration_bots_botint_billing_466a86_idx_and_more'),
        ('workspaces', '0003_rename_logo_workspace_photo_url'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='savedrun',
            name='bots_savedr_workflo_aa2d32_idx',
        ),
        migrations.AddIndex(
            model_name='savedrun',
            index=models.Index(fields=['workflow', 'uid', 'updated_at', 'workspace'], name='bots_savedr_workflo_980e2b_idx'),
        ),
    ]
