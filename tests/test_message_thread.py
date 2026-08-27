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
from daras_ai_v2.web_widget_embed import (
    chat_widget_input_to_request_body,
    get_chat_widget_messages,
)
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


def test_chat_widget_moves_run_metadata_into_history(db_fixtures):
    sr, _ = _make_sr_with_thread(uid="user-a", title="prior")
    request_body, _ = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "hello",
            "raw_input_text": "hello",
            "raw_output_text": ["raw reply"],
            "output_text": ["display reply"],
            "output_video": ["https://example.com/video.mp4"],
            "output_audio": ["https://example.com/audio.mp3"],
        },
        {"input_prompt": "follow up"},
    )

    assistant_msg = request_body["messages"][1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "raw reply"
    assert assistant_msg["run_url"] == sr.get_app_url()
    assert assistant_msg["extra_content"] == {
        "display_content": "display reply",
        "video": ["https://example.com/video.mp4"],
        "audio": ["https://example.com/audio.mp3"],
    }


def test_get_chat_widget_messages_exports_historical_run_metadata():
    messages = get_chat_widget_messages(
        {
            "messages": [
                {"role": "user", "content": "hello"},
                {
                    "role": "assistant",
                    "content": "raw reply",
                    "run_url": "https://example.com/run-123",
                    "extra_content": {
                        "display_content": "display reply",
                        "video": ["https://example.com/video.mp4"],
                        "audio": ["https://example.com/audio.mp3"],
                    },
                },
            ]
        }
    )

    assistant_msg = messages[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["output_text"] == ["display reply"]
    assert assistant_msg["web_url"] == "https://example.com/run-123"
    assert assistant_msg["output_video"] == ["https://example.com/video.mp4"]
    assert assistant_msg["output_audio"] == ["https://example.com/audio.mp3"]


def test_get_chat_widget_messages_skips_output_cleared_by_builder():
    """The builder clears every ResponseModel field when it edits a workflow, but input_prompt is
    a request field and survives. The orphaned input must not get an empty assistant bubble."""
    messages = get_chat_widget_messages(
        {"input_prompt": "hello", "__run_time": 1.5},
    )

    assert [msg["role"] for msg in messages] == ["user"]


def test_get_chat_widget_messages_keeps_running_run_without_output():
    """A run with no output yet still needs its message - that is what draws the progress state."""
    messages = get_chat_widget_messages(
        {"input_prompt": "hello", "__run_status": "Running..."},
    )

    assert [msg["role"] for msg in messages] == ["user", "assistant"]
    assert messages[1]["type"] == "message_part"


def test_get_chat_widget_messages_keeps_failed_run_without_output():
    messages = get_chat_widget_messages(
        {"input_prompt": "hello", "__error_msg": "it broke"},
    )

    assert [msg["role"] for msg in messages] == ["user", "assistant"]
    assert "it broke" in messages[1]["text"]


def test_get_chat_widget_messages_keeps_media_only_output():
    """Text can be empty on a completed run that answered with audio or video."""
    messages = get_chat_widget_messages(
        {
            "input_prompt": "read this",
            "__run_time": 1.5,
            "output_audio": ["https://example.com/audio.mp3"],
        },
    )

    assert [msg["role"] for msg in messages] == ["user", "assistant"]
    assert messages[1]["output_audio"] == ["https://example.com/audio.mp3"]


def test_video_bots_messages_model_preserves_widget_metadata():
    request = VideoBotsPage.RequestModel.model_validate(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": "raw reply",
                    "run_url": "https://example.com/run-123",
                    "extra_content": {
                        "display_content": "display reply",
                        "video": ["https://example.com/video.mp4"],
                        "audio": ["https://example.com/audio.mp3"],
                    },
                }
            ]
        }
    )

    assert isinstance(request.messages[0], dict)
    assert request.messages[0]["run_url"] == "https://example.com/run-123"
    assert request.messages[0]["extra_content"] == {
        "display_content": "display reply",
        "video": ["https://example.com/video.mp4"],
        "audio": ["https://example.com/audio.mp3"],
    }


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
