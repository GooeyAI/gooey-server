# Generated by Django 4.2.7 on 2024-02-20 16:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0059_savedrun_is_api_call'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='reset_at',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
    ]
