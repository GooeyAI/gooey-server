# Generated by Django 4.2.7 on 2024-07-04 09:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0075_alter_publishedrun_workflow_alter_savedrun_workflow_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='botintegration',
            name='twilio_account_sid',
            field=models.TextField(blank=True, default='', help_text='Twilio account sid as found on twilio.com/console (mandatory)'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_asr_language',
            field=models.TextField(default='en-US', help_text='The language to use for Twilio ASR (https://www.twilio.com/docs/voice/twiml/gather#languagetags)'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_auth_token',
            field=models.TextField(blank=True, default='', help_text='Twilio auth token as found on twilio.com/console (mandatory)'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_default_to_gooey_asr',
            field=models.BooleanField(default=False, help_text="If true, the bot will use Gooey ASR for speech recognition instead of Twilio's when available on the attached run"),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_default_to_gooey_tts',
            field=models.BooleanField(default=False, help_text="If true, the bot will use Gooey TTS for text to speech instead of Twilio's when available on the attached run"),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_initial_audio_url',
            field=models.TextField(blank=True, default='', help_text='The initial audio url to play to the user when a call is started'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_initial_text',
            field=models.TextField(blank=True, default='', help_text='The initial text to send to the user when a call is started'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_phone_number',
            field=models.TextField(blank=True, default='', help_text='Twilio unformatted phone number as found on twilio.com/console/phone-numbers/incoming (mandatory)'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_phone_number_sid',
            field=models.TextField(blank=True, default='', help_text='Twilio phone number sid as found on twilio.com/console/phone-numbers/incoming (mandatory)'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_use_missed_call',
            field=models.BooleanField(default=False, help_text="If true, the bot will reject incoming calls and call back the user instead so they don't get charged for the call"),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_voice',
            field=models.TextField(default='woman', help_text="The voice to use for Twilio TTS ('man', 'woman', or Amazon Polly/Google Voices: https://www.twilio.com/docs/voice/twiml/say/text-speech#available-voices-and-languages)"),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_waiting_audio_url',
            field=models.TextField(blank=True, default='', help_text='The audio url to play to the user while waiting for a response if using voice'),
        ),
        migrations.AddField(
            model_name='botintegration',
            name='twilio_waiting_text',
            field=models.TextField(blank=True, default='', help_text='The text to send to the user while waiting for a response if using sms'),
        ),
        migrations.AddField(
            model_name='conversation',
            name='twilio_phone_number',
            field=models.TextField(blank=True, default='', help_text="User's Twilio phone number (mandatory)"),
        ),
        migrations.AlterField(
            model_name='botintegration',
            name='platform',
            field=models.IntegerField(choices=[(1, 'Facebook Messenger'), (2, 'Instagram'), (3, 'WhatsApp'), (4, 'Slack'), (5, 'Web'), (6, 'Twilio')], help_text='The platform that the bot is integrated with'),
        ),
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