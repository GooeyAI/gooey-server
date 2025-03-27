# Generated by Django 5.1.3 on 2025-03-27 10:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0026_alter_appusertransaction_plan'),
        ('bots', '0092_alter_publishedrun_workflow_alter_savedrun_workflow_and_more'),
        ('workspaces', '0010_workspace_banner_url'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='publishedrun',
            name='bots_publis_updated_af6358_idx',
        ),
        migrations.RemoveIndex(
            model_name='publishedrun',
            name='bots_publis_is_appr_a989ec_idx',
        ),
        migrations.AddField(
            model_name='publishedrun',
            name='team_permission',
            field=models.IntegerField(choices=[(1, 'Can View'), (2, 'Can Find'), (3, 'Internal'), (4, 'Can Edit')], default=4),
        ),
        migrations.AddField(
            model_name='publishedrunversion',
            name='team_permission',
            field=models.IntegerField(choices=[(1, 'Can View'), (2, 'Can Find'), (3, 'Internal'), (4, 'Can Edit')], default=4),
        ),
        migrations.AlterField(
            model_name='publishedrun',
            name='visibility',
            field=models.IntegerField(choices=[(1, 'Can View'), (2, 'Can Find'), (3, 'Internal'), (4, 'Can Edit')], default=2),
        ),
        migrations.AlterField(
            model_name='publishedrunversion',
            name='visibility',
            field=models.IntegerField(choices=[(1, 'Can View'), (2, 'Can Find'), (3, 'Internal'), (4, 'Can Edit')], default=1),
        ),
        migrations.AddIndex(
            model_name='publishedrun',
            index=models.Index(fields=['is_approved_example', 'visibility', 'team_permission', 'published_run_id', 'updated_at', 'workflow', 'example_priority'], name='bots_publis_is_appr_ca553a_idx'),
        ),
        migrations.AddIndex(
            model_name='publishedrun',
            index=models.Index(fields=['-updated_at', 'workspace', 'created_by', 'visibility', 'team_permission'], name='bots_publis_updated_4b8b73_idx'),
        ),
    ]
