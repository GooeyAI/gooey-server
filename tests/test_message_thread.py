import pytest
from django.core.management import call_command

from bots.models import (
    BotIntegration,
    Conversation,
    MessageThread,
    Platform,
    SavedRun,
    Workflow,
    get_default_published_run_workspace,
)
from daras_ai_v2.web_widget_embed import chat_widget_input_to_request_body
from recipes.VideoBots import VideoBotsPage
from routers.api import create_new_run
from workspaces.models import Workspace


def test_run_attaches_to_passed_thread_and_sets_pointers(
    db_fixtures, force_authentication
):
    thread = MessageThread.objects.create(title="hello")
    sr = _create_run(force_authentication, message_thread=thread)

    assert sr.message_thread == thread
    thread.refresh_from_db()
    assert thread.first_run == sr
    assert thread.last_run == sr


def test_second_run_advances_last_run_only(db_fixtures, force_authentication):
    thread = MessageThread.objects.create(title="hello")
    sr1 = _create_run(force_authentication, message_thread=thread)
    sr2 = _create_run(force_authentication, message_thread=thread)

    thread.refresh_from_db()
    assert thread.first_run == sr1
    assert thread.last_run == sr2
    assert set(thread.saved_runs.all()) == {sr1, sr2}


def test_run_without_thread_autocreates_thread(db_fixtures, force_authentication):
    sr = _create_run(force_authentication)

    assert sr.message_thread is not None
    assert sr.message_thread.first_run == sr
    assert sr.message_thread.last_run == sr


def test_widget_reuses_thread_when_prev_output_exists(transactional_db):
    thread = MessageThread.objects.create(title="hello")
    sr = _saved_run(message_thread=thread)
    state = {
        "raw_input_text": "hi",
        "raw_output_text": ["hello!"],
        "messages": [],
    }

    request_body, message_thread = chat_widget_input_to_request_body(
        sr, state, {"input_prompt": "next question"}
    )
    assert message_thread == thread
    assert len(request_body["messages"]) == 2


def test_widget_no_thread_on_first_message(transactional_db):
    sr = _saved_run(message_thread=MessageThread.objects.create(title="hello"))

    request_body, message_thread = chat_widget_input_to_request_body(
        sr, {}, {"input_prompt": "first question"}
    )
    assert message_thread is None
    assert "messages" not in request_body


@pytest.mark.xfail(
    reason="SavedRun.message_thread uses on_delete=CASCADE: deleting a "
    "MessageThread permanently deletes every SavedRun attached to it",
    strict=True,
)
def test_deleting_message_thread_preserves_saved_runs(transactional_db):
    thread = MessageThread.objects.create(title="hello")
    sr = _saved_run(message_thread=thread)

    thread.delete()
    assert SavedRun.objects.filter(pk=sr.pk).exists()


@pytest.mark.xfail(
    reason="Conversation -> MessageThread (CASCADE) -> SavedRun (CASCADE): "
    "deleting a Conversation now deletes the run history, which a "
    "Conversation delete never did before this branch",
    strict=True,
)
def test_deleting_conversation_preserves_saved_runs(transactional_db):
    convo = Conversation.objects.create(
        bot_integration=BotIntegration.objects.create(platform=Platform.WEB),
    )
    thread = MessageThread.objects.create(title="hello", bot_conversation=convo)
    sr = _saved_run(message_thread=thread)

    convo.delete()
    assert SavedRun.objects.filter(pk=sr.pk).exists()


@pytest.mark.xfail(
    reason="migration 0128 records first_run/last_run with on_delete=CASCADE "
    "but the model declares SET_NULL, so makemigrations detects drift",
    strict=True,
)
def test_no_pending_model_changes(transactional_db):
    call_command("makemigrations", "bots", check_changes=True, dry_run=True)


@pytest.mark.xfail(
    reason="MessageThreadAdmin.view_first_run/view_last_run call "
    "change_obj_url(None) for threads whose runs were deleted (SET_NULL) or "
    "never set, crashing the admin changelist",
    strict=True,
    raises=AttributeError,
)
def test_admin_handles_thread_without_runs(transactional_db):
    from django.contrib.admin.sites import AdminSite

    from bots.admin import MessageThreadAdmin

    thread = MessageThread.objects.create(title="hello")
    model_admin = MessageThreadAdmin(MessageThread, AdminSite())
    model_admin.view_first_run(thread)
    model_admin.view_last_run(thread)


@pytest.mark.xfail(
    reason="when the previous run produced no output (failed/cancelled), the "
    "widget passes message_thread=None and the retry starts a brand-new "
    "thread instead of continuing sr.message_thread",
    strict=True,
)
def test_failed_run_retry_stays_in_same_thread(transactional_db):
    thread = MessageThread.objects.create(title="hello")
    sr = _saved_run(message_thread=thread)
    failed_state = {
        "raw_input_text": "hi",
        "raw_output_text": [""],  # run failed, no output
    }

    _, message_thread = chat_widget_input_to_request_body(
        sr, failed_state, {"input_prompt": "retry"}
    )
    assert message_thread == thread


def _create_run(user, **defaults) -> SavedRun:
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    state = VideoBotsPage.get_root_pr().saved_run.state
    request_body = VideoBotsPage.get_example_request(state)[1].copy()
    _, sr = create_new_run(
        page_cls=VideoBotsPage,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=request_body,
        **defaults,
    )
    sr.refresh_from_db()
    return sr


def _saved_run(**kwargs) -> SavedRun:
    return SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid="test_uid",
        **kwargs,
    )
