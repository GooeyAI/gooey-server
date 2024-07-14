# Generated by Django 4.2.7 on 2024-07-14 20:51

from django.db import migrations, models


def forwards_func(apps, schema_editor):
    from payments.plans import PricingPlan
    from app_users.models import TransactionReason

    # We get the model from the versioned app registry;
    # if we directly import it, it'll be the wrong version
    AppUserTransaction = apps.get_model("app_users", "AppUserTransaction")
    db_alias = schema_editor.connection.alias
    objects = AppUserTransaction.objects.using(db_alias)

    for transaction in objects.all():
        if transaction.amount <= 0:
            transaction.reason = TransactionReason.DEDUCT
        else:
            # For old transactions, we didn't have a subscription field.
            # It just so happened that all monthly subscriptions we offered had
            # different amounts from the one-time purchases.
            # This uses that heuristic to determine whether a transaction
            # was a subscription payment or a one-time purchase.
            transaction.reason = TransactionReason.ADDON
            for plan in PricingPlan:
                if (
                    transaction.amount == plan.credits
                    and transaction.charged_amount == plan.monthly_charge * 100
                ):
                    transaction.plan = plan.db_value
                    transaction.reason = TransactionReason.SUBSCRIBE
        transaction.save(update_fields=["reason", "plan"])


class Migration(migrations.Migration):

    dependencies = [
        ('app_users', '0017_alter_appuser_subscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='appusertransaction',
            name='plan',
            field=models.IntegerField(blank=True, choices=[(1, 'Basic Plan'), (2, 'Premium Plan'), (3, 'Starter'), (4, 'Creator'), (5, 'Business'), (6, 'Enterprise / Agency')], default=None, help_text="User's plan at the time of this transaction.", null=True),
        ),
        migrations.AddField(
            model_name='appusertransaction',
            name='reason',
            field=models.IntegerField(choices=[(1, 'Deduct'), (2, 'Addon'), (3, 'Subscribe'), (4, 'Sub-Create'), (5, 'Sub-Cycle'), (6, 'Sub-Update'), (7, 'Auto-Recharge')], default=0, help_text='The reason for this transaction.<br><br>Deduct: Credits deducted due to a run.<br>Addon: User purchased an add-on.<br>Subscribe: Applies to subscriptions where no distinction was made between create, update and cycle.<br>Sub-Create: A subscription was created.<br>Sub-Cycle: A subscription advanced into a new period.<br>Sub-Update: A subscription was updated.<br>Auto-Recharge: Credits auto-recharged due to low balance.'),
        ),
        migrations.RunPython(forwards_func, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='appusertransaction',
            name='reason',
            field=models.IntegerField(choices=[(1, 'Deduct'), (2, 'Addon'), (3, 'Subscribe'), (4, 'Sub-Create'), (5, 'Sub-Cycle'), (6, 'Sub-Update'), (7, 'Auto-Recharge')], help_text='The reason for this transaction.<br><br>Deduct: Credits deducted due to a run.<br>Addon: User purchased an add-on.<br>Subscribe: Applies to subscriptions where no distinction was made between create, update and cycle.<br>Sub-Create: A subscription was created.<br>Sub-Cycle: A subscription advanced into a new period.<br>Sub-Update: A subscription was updated.<br>Auto-Recharge: Credits auto-recharged due to low balance.'),
        ),
    ]