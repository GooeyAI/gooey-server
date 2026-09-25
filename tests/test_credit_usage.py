from unittest.mock import patch

import pytest
from dateutil.relativedelta import relativedelta

from app_users.models import AppUserTransaction, TransactionReason
from bots.models import AppUser, SavedRun
from bots.models.workflow import Workflow
from widgets.credit_usage import (
    _month_range,
    _monthly_usage_by_workflow,
    _this_month,
    render_credit_usage,
)
from workspaces.models import Workspace


def test_monthly_usage_groups_deductions_by_month_and_recipe(transactional_db):
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    workspace = Workspace(name="myteam", created_by=user, is_personal=True)
    workspace.create_with_owner()
    this_month = _this_month()
    months = _month_range(this_month - relativedelta(months=5), this_month)

    def deduct(amount, month, workflow=None, reason=TransactionReason.DEDUCT):
        txn = AppUserTransaction.objects.create(
            workspace=workspace,
            user=user,
            invoice_id=f"test_{AppUserTransaction.objects.count()}",
            amount=amount,
            end_balance=0,
            reason=reason,
            created_at=month + relativedelta(days=3),
        )
        if workflow is not None:
            SavedRun.objects.create(
                workflow=workflow, workspace=workspace, transaction=txn
            )

    deduct(-10, months[0], Workflow.VIDEO_BOTS)
    deduct(-5, months[0], Workflow.VIDEO_BOTS)
    deduct(-7, months[-1], Workflow.VIDEO_BOTS)
    deduct(-3, months[2], Workflow.COMPARE_LLM)
    deduct(-4, months[2])  # no saved run
    deduct(-99, months[0] - relativedelta(months=1), Workflow.VIDEO_BOTS)  # too old
    deduct(500, months[1], reason=TransactionReason.ADDON)  # a purchase
    deduct(-8, months[-1] + relativedelta(months=1), Workflow.VIDEO_BOTS)  # after

    series = _monthly_usage_by_workflow(workspace, months)

    assert [(s.id, s.credits) for s in series] == [
        (Workflow.VIDEO_BOTS.short_slug, [15, 0, 0, 0, 0, 7]),
        ("unattributed", [0, 0, 4, 0, 0, 0]),
        (Workflow.COMPARE_LLM.short_slug, [0, 0, 3, 0, 0, 0]),
    ]


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (None, None, (-5, 0)),
        ("2020-01", None, (-35, 0)),  # clamped to the picker's reach
        (-2, -4, (-4, -2)),  # reversed ranges are swapped
        (-3, "garbage", (-3, 0)),
        (None, -10, (-15, -10)),
    ],
)
def test_render_credit_usage_range(transactional_db, start, end, expected):
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    workspace = Workspace(name="myteam", created_by=user, is_personal=True)
    workspace.create_with_owner()
    this_month = _this_month()

    def month(value):
        if isinstance(value, int):
            return (this_month + relativedelta(months=value)).strftime("%Y-%m")
        return value

    with patch("gooey_gui.model_component") as model_component:
        render_credit_usage(
            workspace,
            workspace_name="myteam",
            billing_href="/account/billing/",
            base_href="/account/usage/",
            start=month(start),
            end=month(end),
        )
    props = model_component.call_args.args[0]
    assert (props.months[0], props.months[-1]) == tuple(month(v) for v in expected)
    assert [p.active for p in props.presets][:3] == [
        False,
        start is None and end is None,
        False,
    ]
