# Generated by Django 4.2.7 on 2024-05-10 14:32

import bots.custom_fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0070_botintegrationanalysisrun_cooldown_period_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='botintegration',
            name='by_line',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='conversation_starters',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='descripton',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='photo_url',
            field=bots.custom_fields.CustomURLField(blank=True, default='', max_length=2048),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='website_url',
            field=bots.custom_fields.CustomURLField(blank=True, default='', max_length=2048),
        ),
        migrations.AlterField(
            model_name='botintegration',
            name='platform',
            field=models.IntegerField(choices=[(1, 'Facebook Messenger'), (2, 'Instagram'), (3, 'WhatsApp'), (4, 'Slack'), (5, 'Web')], help_text='The platform that the bot is integrated with'),
        ),
    ]
