# Generated by Django 4.2.7 on 2024-09-02 14:07

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0001_initial'),
        ('app_users', '0019_alter_appusertransaction_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='appusertransaction',
            name='workspace',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='workspaces.workspace'),
        ),
        migrations.AlterField(
            model_name='appusertransaction',
            name='user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='app_users.appuser'),
        ),
    ]