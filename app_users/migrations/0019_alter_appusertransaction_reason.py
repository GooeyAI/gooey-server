# Generated by Django 4.2.7 on 2024-07-14 21:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0018_appusertransaction_plan_appusertransaction_reason'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appusertransaction',
            name='reason',
            field=models.IntegerField(choices=[(1, 'Deduct'), (2, 'Addon'), (3, 'Subscribe'), (4, 'Sub-Create'), (5, 'Sub-Cycle'), (6, 'Sub-Update'), (7, 'Auto-Recharge')], help_text='The reason for this transaction.<br><br>Deduct: Credits deducted due to a run.<br>Addon: User purchased an add-on.<br>Subscribe: Applies to subscriptions where no distinction was made between create, update and cycle.<br>Sub-Create: A subscription was created.<br>Sub-Cycle: A subscription advanced into a new period.<br>Sub-Update: A subscription was updated.<br>Auto-Recharge: Credits auto-recharged due to low balance.'),
        ),
    ]