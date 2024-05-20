# Generated by Django 4.2.7 on 2024-05-20 14:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0072_botintegration_web_config_extras'),
    ]

    operations = [
        migrations.AddField(
            model_name='savedrun',
            name='retention_policy',
            field=models.IntegerField(choices=[(0, 'Keep'), (1, 'Delete')], default=0),
        ),
    ]