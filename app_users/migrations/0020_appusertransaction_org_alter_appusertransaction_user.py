# Generated by Django 4.2.7 on 2024-08-13 14:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0005_org_unique_personal_org_per_user'),
        ('app_users', '0019_alter_appusertransaction_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='appusertransaction',
            name='org',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='orgs.org'),
        ),
        migrations.AlterField(
            model_name='appusertransaction',
            name='user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='app_users.appuser'),
        ),
    ]