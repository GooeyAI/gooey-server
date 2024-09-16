from django.utils import timezone

from app_users.models import AppUserTransaction
from bots.models import AppUser
from celeryapp.tasks import run_low_balance_email_check
from daras_ai_v2 import settings
from daras_ai_v2.send_email import pytest_outbox
from workspaces.models import Workspace


def test_dont_send_email_if_feature_is_disabled(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        is_paying=True,
    )
    workspace.create_with_owner()
    settings.LOW_BALANCE_EMAIL_ENABLED = False
    run_low_balance_email_check(workspace)
    assert not pytest_outbox


def test_dont_send_email_if_user_is_not_paying(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        is_paying=False,
    )
    workspace.create_with_owner()

    settings.LOW_BALANCE_EMAIL_ENABLED = True
    run_low_balance_email_check(workspace)
    assert not pytest_outbox


def test_dont_send_email_if_user_has_enough_balance(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        balance=500,
        is_paying=True,
    )
    workspace.create_with_owner()

    settings.LOW_BALANCE_EMAIL_CREDITS = 100
    settings.LOW_BALANCE_EMAIL_ENABLED = True
    run_low_balance_email_check(workspace)
    assert not pytest_outbox


def test_dont_send_email_if_user_has_been_emailed_recently(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        balance=66,
        is_paying=True,
        low_balance_email_sent_at=timezone.now(),
    )
    workspace.create_with_owner()

    settings.LOW_BALANCE_EMAIL_ENABLED = True
    settings.LOW_BALANCE_EMAIL_DAYS = 1
    settings.LOW_BALANCE_EMAIL_CREDITS = 100
    run_low_balance_email_check(workspace)
    assert not pytest_outbox


def test_send_email_if_user_has_been_email_recently_but_made_a_purchase(
    transactional_db,
):
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    workspace = Workspace(
        name="myteam",
        created_by=user,
        is_personal=True,
        balance=22,
        is_paying=True,
        low_balance_email_sent_at=timezone.now(),
    )
    workspace.create_with_owner()

    AppUserTransaction.objects.create(
        invoice_id="test_invoice_1",
        user=user,
        workspace=workspace,
        amount=100,
        created_at=timezone.now(),
        end_balance=100,
    )
    AppUserTransaction.objects.create(
        invoice_id="test_invoice_2",
        user=user,
        workspace=workspace,
        amount=-78,
        created_at=timezone.now(),
        end_balance=22,
    )

    settings.LOW_BALANCE_EMAIL_ENABLED = True
    settings.LOW_BALANCE_EMAIL_DAYS = 1
    settings.LOW_BALANCE_EMAIL_CREDITS = 100
    run_low_balance_email_check(workspace)

    assert len(pytest_outbox) == 1
    assert " 22" in pytest_outbox[0]["html_body"]
    assert " 78" in pytest_outbox[0]["html_body"]

    pytest_outbox.clear()
    run_low_balance_email_check(workspace)
    assert not pytest_outbox


def test_send_email(transactional_db):
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    workspace = Workspace(
        name="myteam",
        created_by=user,
        is_personal=True,
        is_paying=True,
        balance=66,
    )
    workspace.create_with_owner()

    AppUserTransaction.objects.create(
        invoice_id="test_invoice_1",
        workspace=workspace,
        amount=-100,
        created_at=timezone.now() - timezone.timedelta(days=2),
        end_balance=150 + 66,
    )
    AppUserTransaction.objects.create(
        invoice_id="test_invoice_2",
        workspace=workspace,
        amount=-150,
        created_at=timezone.now(),
        end_balance=66,
    )
    settings.LOW_BALANCE_EMAIL_ENABLED = True
    settings.LOW_BALANCE_EMAIL_DAYS = 1
    settings.LOW_BALANCE_EMAIL_CREDITS = 100

    run_low_balance_email_check(workspace)
    assert len(pytest_outbox) == 1
    body = pytest_outbox[0]["html_body"]
    assert " 66" in body
    assert " 150" in body
    assert " pm:unsubscribe" in body
    assert " 100" not in body

    pytest_outbox.clear()
    run_low_balance_email_check(workspace)
    assert not pytest_outbox
