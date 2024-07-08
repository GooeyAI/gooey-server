# Generated by Django 4.2.7 on 2024-07-05 13:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0075_alter_publishedrun_workflow_alter_savedrun_workflow_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workflowmetadata',
            name='default_image',
            field=models.URLField(blank=True, default='', help_text='Image shown on explore page'),
        ),
        migrations.AlterField(
            model_name='workflowmetadata',
            name='help_url',
            field=models.URLField(blank=True, default='', help_text='(Not implemented)'),
        ),
        migrations.AlterField(
            model_name='workflowmetadata',
            name='meta_keywords',
            field=models.JSONField(blank=True, default=list, help_text='(Not implemented)'),
        ),
        migrations.AlterField(
            model_name='workflowmetadata',
            name='short_title',
            field=models.TextField(help_text='Title used in breadcrumbs'),
        ),
    ]