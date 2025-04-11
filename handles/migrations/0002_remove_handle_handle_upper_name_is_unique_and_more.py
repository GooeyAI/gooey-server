# Generated by Django 5.1.3 on 2025-03-25 11:06

import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('handles', '0001_initial'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='handle',
            name='handle_upper_name_is_unique',
        ),
        migrations.AddConstraint(
            model_name='handle',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Upper('name'), name='handle_upper_name_is_unique', violation_error_message='This handle is already taken'),
        ),
    ]
