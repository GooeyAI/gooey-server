# Generated by Django 5.1.3 on 2025-01-08 12:04

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0023_alter_appusertransaction_workspace'),
        ('handles', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appuser',
            name='handle',
            field=models.OneToOneField(blank=True, default=None, help_text='[deprecated] use workspace.handle instead', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='user', to='handles.handle'),
        ),
    ]
