# Generated by Django 5.1.2 on 2024-11-07 12:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0003_rename_logo_workspace_photo_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workspaceinvite',
            name='role',
            field=models.IntegerField(choices=[(1, 'Owner'), (2, 'Admin'), (3, 'Member')], default=3),
        ),
        migrations.AlterField(
            model_name='workspacemembership',
            name='role',
            field=models.IntegerField(choices=[(1, 'Owner'), (2, 'Admin'), (3, 'Member')], default=3),
        ),
    ]
