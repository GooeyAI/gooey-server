# Generated by Django 4.2.7 on 2024-02-22 22:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0059_savedrun_is_api_call'),
    ]

    operations = [
        migrations.AddField(
            model_name='botintegration',
            name='wa_business_access_token',
            field=models.TextField(blank=True, default=None, help_text="Bot's WhatsApp Business access token (mandatory) -- has these scopes: ['whatsapp_business_management', 'whatsapp_business_messaging', 'public_profile']", null=True),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='wa_business_account_name',
            field=models.TextField(blank=True, default='', help_text="Bot's WhatsApp Business API account name (only for display)"),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='wa_business_message_template_namespace',
            field=models.TextField(blank=True, default='', help_text="Bot's WhatsApp Business API message template namespace"),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='wa_business_name',
            field=models.TextField(blank=True, default='', help_text="Bot's WhatsApp Business API name (only for display)"),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='wa_business_user_id',
            field=models.TextField(blank=True, default=None, help_text="Bot's WhatsApp Business API user id (mandatory)", null=True),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='wa_business_waba_id',
            field=models.TextField(blank=True, default=None, help_text="Bot's WhatsApp Business API WABA id (mandatory) -- this is the one seen on https://business.facebook.com/settings/whatsapp-business-accounts/", null=True),
        ),
    ]
