from app_users.models import AppUser
from bots.models import (
    BotIntegration,
    Conversation,
    Platform,
    SavedRun,
    Workflow,
    get_default_published_run_workspace,
)
from bots.models.message_thread import MessageThread
from daras_ai_v2.web_widget_embed import chat_widget_input_to_request_body
from recipes.VideoBots import VideoBotsPage
from routers.api import create_new_run
from workspaces.models import Workspace


def test_chat_widget_new_conversation_returns_no_thread(db_fixtures):
    sr, thread = _make_sr_with_thread(uid="user-a", title="prior")
    request_body, message_thread = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "",
            "raw_input_text": "",
            "input_images": None,
            "input_audio": None,
            "input_documents": None,
            "raw_output_text": ["prior reply"],
        },
        {"input_prompt": "fresh start"},
    )

    assert request_body["input_prompt"] == "fresh start"
    assert message_thread is None
    assert thread.id  # existing thread was not deleted


def test_chat_widget_continues_thread_with_prior_input_prompt(db_fixtures):
    sr, thread = _make_sr_with_thread(uid="user-a", title="prior")
    _, message_thread = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "hello",
            "raw_input_text": "hello",
            "raw_output_text": ["hi there"],
        },
        {"input_prompt": "follow up"},
    )

    assert message_thread == thread


def test_chat_widget_continues_thread_with_raw_input_only(db_fixtures):
    sr, thread = _make_sr_with_thread(uid="user-a", title="prior")
    _, message_thread = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "",
            "raw_input_text": "transcribed hello",
            "raw_output_text": ["hi there"],
        },
        {"input_prompt": "follow up"},
    )

    assert message_thread == thread


def test_chat_widget_continues_thread_without_prior_output(db_fixtures):
    sr, thread = _make_sr_with_thread(uid="user-a", title="prior")
    request_body, message_thread = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "hello",
            "raw_input_text": "hello",
            "raw_output_text": [],
        },
        {"input_prompt": "retry"},
    )

    assert message_thread == thread
    assert "messages" not in request_body


def test_chat_widget_continues_thread_with_prior_media(db_fixtures):
    sr, thread = _make_sr_with_thread(uid="user-a", title="prior")
    _, message_thread = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "",
            "raw_input_text": "",
            "input_images": ["https://example.com/a.png"],
            "raw_output_text": ["nice photo"],
        },
        {"input_prompt": "what is this?"},
    )

    assert message_thread == thread


def test_create_new_run_creates_thread_and_sets_first_last(
    db_fixtures, force_authentication
):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    request_body = _video_bots_request_body(input_prompt="first message")

    _, sr = create_new_run(
        page_cls=VideoBotsPage,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=request_body,
    )
    sr.refresh_from_db()

    assert sr.message_thread_id
    thread = sr.message_thread
    assert thread.title == "first message"
    assert thread.first_run_id == sr.id
    assert thread.last_run_id == sr.id


def test_create_new_run_reuses_thread_for_same_user(db_fixtures, force_authentication):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    request_body = _video_bots_request_body(input_prompt="first")
    _, first_sr = create_new_run(
        page_cls=VideoBotsPage,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=request_body,
    )
    thread = first_sr.message_thread

    _, second_sr = create_new_run(
        page_cls=VideoBotsPage,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=_video_bots_request_body(input_prompt="second"),
        message_thread=thread,
    )
    second_sr.refresh_from_db()
    thread.refresh_from_db()

    assert second_sr.message_thread_id == thread.id
    assert thread.first_run_id == first_sr.id
    assert thread.last_run_id == second_sr.id
    assert thread.saved_runs.count() == 2


def test_create_new_run_rejects_other_users_thread(db_fixtures, force_authentication):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    other = AppUser.objects.create(
        uid="other-user",
        is_anonymous=False,
        balance=1000,
    )
    other_sr, other_thread = _make_sr_with_thread(uid=other.uid, title="other chat")

    _, sr = create_new_run(
        page_cls=VideoBotsPage,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=_video_bots_request_body(input_prompt="mine"),
        message_thread=other_thread,
    )
    sr.refresh_from_db()
    other_thread.refresh_from_db()

    assert sr.message_thread_id != other_thread.id
    assert other_thread.last_run_id == other_sr.id
    assert sr.message_thread.first_run_id == sr.id


def test_create_new_run_rejects_thread_when_last_run_cleared(
    db_fixtures, force_authentication
):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    other = AppUser.objects.create(
        uid="other-user-2",
        is_anonymous=False,
        balance=1000,
    )
    other_sr, other_thread = _make_sr_with_thread(uid=other.uid, title="orphaned")
    other_thread.last_run = None
    other_thread.save(update_fields=["last_run"])

    _, sr = create_new_run(
        page_cls=VideoBotsPage,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=_video_bots_request_body(input_prompt="mine"),
        message_thread=other_thread,
    )
    sr.refresh_from_db()

    assert sr.message_thread_id != other_thread.id
    assert other_sr.message_thread_id == other_thread.id


def test_bot_conversation_reuses_same_message_thread(db_fixtures):
    bi = BotIntegration.objects.create(platform=Platform.WEB, name="test bi 2")
    convo = Conversation.objects.create(bot_integration=bi, web_user_id="web-2")

    thread1 = MessageThread.objects.get_or_create(
        bot_conversation=convo,
        defaults=dict(title="hello"),
    )[0]
    thread2 = MessageThread.objects.get_or_create(
        bot_conversation=convo,
        defaults=dict(title="world"),
    )[0]

    assert thread1.id == thread2.id
    assert thread1.title == "hello"


def _make_sr_with_thread(*, uid: str, title: str) -> tuple[SavedRun, MessageThread]:
    thread = MessageThread.objects.create(title=title)
    sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id=f"run-{uid}-{title}",
        uid=uid,
        message_thread=thread,
        state={"input_prompt": title, "raw_input_text": title},
    )
    thread.first_run = sr
    thread.last_run = sr
    thread.save(update_fields=["first_run", "last_run"])
    return sr, thread


def _video_bots_request_body(*, input_prompt: str) -> dict:
    state = VideoBotsPage.get_root_pr().saved_run.state.copy()
    request_body = VideoBotsPage.get_example_request(state)[1].copy()
    request_body["input_prompt"] = input_prompt
    return request_body
