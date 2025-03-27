# Generated by Django 5.1.3 on 2025-03-25 11:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0092_alter_publishedrun_workflow_alter_savedrun_workflow_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='publishedrun',
            name='is_public',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='publishedrun',
            name='visibility',
            field=models.IntegerField(choices=[(1, 'Unlisted'), (2, 'Public'), (3, 'Internal And Editable'), (4, 'Internal And View Only')], default=1),
        ),
        migrations.AlterField(
            model_name='publishedrunversion',
            name='visibility',
            field=models.IntegerField(choices=[(1, 'Unlisted'), (2, 'Public'), (3, 'Internal And Editable'), (4, 'Internal And View Only')], default=1),
        ),
    ]
