import pytest
from django.utils import timezone

from bots.models import (
    AppUser,
    BotIntegration,
    Platform,
    PublishedRun,
    PublishedRunVersion,
    SavedRun,
    Workflow,
)
from celeryapp.tasks import out_of_credits_email_check, post_runner_tasks
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import InsufficientCredits
from daras_ai_v2.send_email import pytest_outbox
from workspaces.models import Workspace


@pytest.fixture(autouse=True)
def _isolate_email_settings(monkeypatch):
    monkeypatch.setattr(settings, "OUT_OF_CREDITS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "OUT_OF_CREDITS_EMAIL_DAYS", 1)
    monkeypatch.setattr(settings, "LOW_BALANCE_EMAIL_ENABLED", False)
    pytest_outbox.clear()


def _make_sr_and_bi(*, workspace, bot_name="My Bot", is_api_call=True):
    recipe_sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        uid=workspace.created_by.uid,
        workspace=workspace,
    )
    pr = PublishedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        title=bot_name,
        saved_run=recipe_sr,
        created_by=workspace.created_by,
    )
    version = PublishedRunVersion.objects.create(
        version_id="test_version",
        published_run=pr,
        saved_run=recipe_sr,
        title=bot_name,
    )
    bi = BotIntegration.objects.create(
        name=bot_name,
        workspace=workspace,
        platform=Platform.WHATSAPP,
        saved_run=recipe_sr,
        published_run=pr,
    )
    sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid=workspace.created_by.uid,
        workspace=workspace,
        is_api_call=is_api_call,
        parent=recipe_sr,
        parent_version=version,
    )
    return sr, bi


def test_dont_send_out_of_credits_email_if_feature_is_disabled(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        is_paying=True,
    )
    workspace.create_with_owner()
    sr, _ = _make_sr_and_bi(workspace=workspace)

    settings.OUT_OF_CREDITS_EMAIL_ENABLED = False  # override fixture default
    out_of_credits_email_check(sr)
    assert not pytest_outbox


def test_dont_send_out_of_credits_email_if_workspace_not_paying(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        is_paying=False,
    )
    workspace.create_with_owner()
    sr, _ = _make_sr_and_bi(workspace=workspace)

    out_of_credits_email_check(sr)
    assert not pytest_outbox


def test_dont_send_out_of_credits_email_if_recently_emailed(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        is_paying=True,
        out_of_credits_email_sent_at=timezone.now(),
    )
    workspace.create_with_owner()
    sr, _ = _make_sr_and_bi(workspace=workspace)

    out_of_credits_email_check(sr)
    assert not pytest_outbox


def test_dont_send_out_of_credits_email_if_not_api_call(transactional_db):
    workspace = Workspace(
        name="myteam",
        created_by=AppUser.objects.create(uid="test_user", is_anonymous=False),
        is_personal=True,
        is_paying=True,
    )
    workspace.create_with_owner()
    sr, _ = _make_sr_and_bi(workspace=workspace, is_api_call=False)
    sr.error_type = InsufficientCredits.__name__
    sr.save(update_fields=["error_type"])

    post_runner_tasks(sr.id)
    assert not pytest_outbox


def test_send_out_of_credits_email(transactional_db):
    user = AppUser.objects.create(
        uid="test_user",
        is_anonymous=False,
        email="owner@example.com",
    )
    workspace = Workspace(
        name="myteam",
        created_by=user,
        is_personal=True,
        is_paying=True,
    )
    workspace.create_with_owner()
    sr, _ = _make_sr_and_bi(workspace=workspace, bot_name="Support Bot")

    out_of_credits_email_check(sr)
    assert len(pytest_outbox) == 1

    msg = pytest_outbox[0]
    assert msg["to_address"] == "owner@example.com"
    body = msg["html_body"]
    assert "Support Bot" in body
    assert "unable to respond" in body
    assert "run out of Gooey.AI credits" in body
    assert "Buy Credits" in body
    assert "run_id=test_run" in body

    pytest_outbox.clear()
    out_of_credits_email_check(sr)
    assert not pytest_outbox
