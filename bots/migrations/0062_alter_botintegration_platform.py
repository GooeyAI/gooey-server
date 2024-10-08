# Generated by Django 4.2.7 on 2024-03-13 15:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0061_botintegration_wa_business_access_token_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='botintegration',
            name='platform',
            field=models.IntegerField(choices=[(1, 'Facebook'), (2, 'Instagram'), (3, 'WhatsApp'), (4, 'Slack')], help_text='The platform that the bot is integrated with'),
        ),
    ]
