# Generated by Django 4.2.7 on 2024-03-29 11:56

import bots.custom_fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0014_appuser_handle'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='bio',
            field=bots.custom_fields.StrippedTextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='appuser',
            name='company',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='appuser',
            name='github_username',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='appuser',
            name='website_url',
            field=bots.custom_fields.ValidatedURLField(blank=True, default='', max_length=2048),
        ),
    ]
