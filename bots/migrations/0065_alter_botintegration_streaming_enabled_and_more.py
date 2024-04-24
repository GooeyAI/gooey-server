# Generated by Django 4.2.7 on 2024-04-16 14:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0064_botintegration_web_allowed_origins_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='botintegration',
            name='streaming_enabled',
            field=models.BooleanField(default=False, help_text='If set, the bot will stream messages to the frontend (Slack & Web only)'),
        ),
        migrations.AddIndex(
            model_name='publishedrun',
            index=models.Index(models.F('created_by'), models.F('visibility'), models.OrderBy(models.F('updated_at'), descending=True), name='published_run_cre_vis_upd_idx'),
        ),
        migrations.AddIndex(
            model_name='publishedrunversion',
            index=models.Index(fields=['changed_by'], name='bots_publis_changed_dd3ca1_idx'),
        ),
        migrations.AddIndex(
            model_name='savedrun',
            index=models.Index(fields=['uid'], name='bots_savedr_uid_d167d4_idx'),
        ),
    ]