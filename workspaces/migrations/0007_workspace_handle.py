# Generated by Django 5.1.3 on 2024-12-04 12:11

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('handles', '0001_initial'),
        ('workspaces', '0006_workspace_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='handle',
            field=models.OneToOneField(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workspace', to='handles.handle'),
        ),
    ]
