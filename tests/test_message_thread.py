import datetime

import pytest

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
from daras_ai_v2.exceptions import UserError
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


def test_chat_widget_stamps_run_url_on_both_entries(db_fixtures):
    sr, _ = _make_sr_with_thread(uid="user-a", title="prior")
    request_body, _ = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "hello",
            "raw_input_text": "hello",
            "raw_output_text": ["raw reply"],
        },
        {"input_prompt": "follow up"},
    )

    user_msg, assistant_msg = request_body["messages"]
    assert user_msg["role"] == "user"
    # outgoing turns keep it in extra_content, which to_llm_body drops wholesale
    assert user_msg["extra_content"]["run_url"] == sr.get_app_url()
    assert assistant_msg["run_url"] == sr.get_app_url()


def test_get_chat_widget_messages_exports_user_web_url():
    messages = get_chat_widget_messages(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                    "extra_content": {"run_url": "https://example.com/run-123"},
                },
                {"role": "user", "content": "from before the change"},
            ]
        }
    )

    assert messages[0]["web_url"] == "https://example.com/run-123"
    # pre-change turns carry no run_url, so the widget hides the edit affordance
    assert "web_url" not in messages[1]


def test_get_chat_widget_messages_sets_web_url_on_live_user_message():
    messages = get_chat_widget_messages(
        {"input_prompt": "hi", "output_text": ["hello"]},
        web_url="https://example.com/run-current",
    )

    assert messages[0]["role"] == "user"
    assert messages[0]["web_url"] == "https://example.com/run-current"


def test_chat_widget_edit_truncates_history_at_edited_turn(db_fixtures):
    current_sr, _ = _make_sr_with_thread(uid="user-a", title="current")
    edit_sr = _make_sr(
        uid="user-a",
        run_id="run-edit-target",
        state={
            "input_prompt": "old question",
            "messages": [
                {"role": "user", "content": "turn one"},
                {"role": "assistant", "content": "reply one"},
            ],
        },
    )
    state = {
        "messages": [
            {"role": "user", "content": "turn one"},
            {"role": "assistant", "content": "reply one"},
            {
                "role": "user",
                "content": "old question",
                "run_url": edit_sr.get_app_url(),
            },
            {
                "role": "assistant",
                "content": "old answer",
                "run_url": edit_sr.get_app_url(),
            },
        ]
    }

    request_body, message_thread = chat_widget_input_to_request_body(
        current_sr, state, {"input_prompt": "new question"}, edit_sr=edit_sr
    )

    # this fixture's edit_sr has no thread, so there is none to hand over
    assert message_thread is None
    assert request_body["input_prompt"] == "new question"
    # the edited turn and everything after it are dropped
    assert request_body["messages"] == [
        {"role": "user", "content": "turn one"},
        {"role": "assistant", "content": "reply one"},
    ]


def test_chat_widget_edit_allows_current_run(db_fixtures):
    current_sr = _make_sr(
        uid="user-a",
        run_id="run-current",
        state={
            "input_prompt": "newest question",
            "messages": [{"role": "user", "content": "turn one"}],
        },
    )

    request_body, _ = chat_widget_input_to_request_body(
        current_sr, current_sr.state, {"input_prompt": "edited"}, edit_sr=current_sr
    )

    assert request_body["input_prompt"] == "edited"
    assert request_body["messages"] == [{"role": "user", "content": "turn one"}]


def test_chat_widget_edit_rejects_run_outside_conversation(db_fixtures):
    current_sr, _ = _make_sr_with_thread(uid="user-a", title="current")
    elsewhere_sr = _make_sr(
        uid="user-a", run_id="run-elsewhere", state={"bot_script": "private prompt"}
    )

    with pytest.raises(UserError):
        chat_widget_input_to_request_body(
            current_sr,
            {"messages": []},
            {"input_prompt": "steal it"},
            edit_sr=elsewhere_sr,
        )


def test_chat_widget_edit_rejects_other_users_run(db_fixtures):
    current_sr, _ = _make_sr_with_thread(uid="user-a", title="current")
    stranger_sr = _make_sr(
        uid="user-b", run_id="run-stranger", state={"bot_script": "private prompt"}
    )
    # even if the history is forged to reference it, the uid check rejects it
    state = {
        "messages": [
            {
                "role": "user",
                "content": "x",
                "run_url": stranger_sr.get_app_url(),
            }
        ]
    }

    with pytest.raises(UserError):
        chat_widget_input_to_request_body(
            current_sr, state, {"input_prompt": "steal it"}, edit_sr=stranger_sr
        )


def test_chat_widget_edit_does_not_mutate_source_run_state(db_fixtures):
    current_sr = _make_sr(
        uid="user-a",
        run_id="run-current-2",
        state={
            "messages": [{"role": "user", "content": "turn one"}],
            "variables": {"foo": "bar"},
        },
    )

    request_body, _ = chat_widget_input_to_request_body(
        current_sr, current_sr.state, {"input_prompt": "edited"}, edit_sr=current_sr
    )
    request_body["messages"].append({"role": "user", "content": "injected"})
    request_body["variables"]["foo"] = "mutated"

    assert current_sr.state["messages"] == [{"role": "user", "content": "turn one"}]
    assert current_sr.state["variables"] == {"foo": "bar"}


def test_chat_widget_edit_hands_the_thread_over_instead_of_forking(db_fixtures):
    """
    An edit keeps the conversation's own thread, so the sidebar shows one row
    that moves - not a new row per edit, titled after the edited message.
    """
    r1, thread = _make_sr_with_thread(uid="user-a", title="first message")
    r2 = _make_thread_run(thread, run_id="run-2", uid="user-a", prompt="second message")

    _, message_thread = chat_widget_input_to_request_body(
        r1,
        {
            "messages": [
                {"role": "user", "content": "first message"},
                {
                    "role": "assistant",
                    "content": "a1",
                    "run_url": r2.get_app_url(),
                },
            ]
        },
        {"input_prompt": "second message edited"},
        edit_sr=r2,
    )

    assert message_thread == thread
    assert thread.title == "first message"  # not retitled to the edited message


def test_chat_widget_edit_leaves_superseded_turns_attached(db_fixtures):
    """
    message_thread is a superseded run's only link back to its conversation, so
    editing must not detach it. Nothing user-facing walks a thread's runs - the
    sidebar and fetch_conversations both key off last_run - so leaving them be
    costs nothing and keeps the abandoned branch traceable.
    """
    r1, thread = _make_sr_with_thread(uid="user-a", title="first message")
    r2 = _make_thread_run(thread, run_id="run-2", uid="user-a", prompt="second message")
    r3 = _make_thread_run(thread, run_id="run-3", uid="user-a", prompt="third message")

    chat_widget_input_to_request_body(
        r1,
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": "a1",
                    "run_url": r2.get_app_url(),
                }
            ]
        },
        {"input_prompt": "second message edited"},
        edit_sr=r2,
    )

    for sr in (r1, r2, r3):
        sr.refresh_from_db()
        assert sr.message_thread == thread
    thread.refresh_from_db()
    assert thread.first_run == r1


def test_chat_widget_stamps_created_at_on_the_user_entry(db_fixtures):
    """
    Only outgoing messages render a timestamp in the widget, so the assistant
    half of the turn doesn't carry one. Stored as isoformat because this goes
    into the run's json state.
    """
    sr, _ = _make_sr_with_thread(uid="user-a", title="prior")
    request_body, _ = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "hello",
            "raw_input_text": "hello",
            "raw_output_text": ["reply"],
        },
        {"input_prompt": "follow up"},
    )

    user_msg, assistant_msg = request_body["messages"]
    assert user_msg["extra_content"]["created_at"] == sr.created_at.isoformat()
    assert "created_at" not in assistant_msg.get("extra_content", {})


def test_get_chat_widget_messages_exports_created_at_on_user_messages():
    messages = get_chat_widget_messages(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                    "extra_content": {"created_at": "2026-08-13T10:30:00+00:00"},
                },
                {"role": "assistant", "content": "reply"},
            ],
            "input_prompt": "latest question",
            "created_at": "2026-08-13T11:00:00+00:00",
        }
    )

    assert messages[0]["created_at"] == "2026-08-13T10:30:00+00:00"
    assert "created_at" not in messages[1]
    # the live turn timestamps from the run currently being viewed
    assert messages[2]["created_at"] == "2026-08-13T11:00:00+00:00"


def test_chat_widget_stamps_run_time_on_the_assistant_entry(db_fixtures):
    """
    How long the answer took is a property of the run that produced it, so it
    rides along with the run url on the assistant half. Named as the streaming
    api's final_response event names it, since both report the same run.
    """
    sr, _ = _make_sr_with_thread(uid="user-a", title="prior")
    sr.run_time = datetime.timedelta(seconds=3.5)
    sr.save(update_fields=["run_time"])

    request_body, _ = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "hello",
            "raw_input_text": "hello",
            "raw_output_text": ["reply"],
        },
        {"input_prompt": "follow up"},
    )

    user_msg, assistant_msg = request_body["messages"]
    assert assistant_msg["run_time_sec"] == 3.5
    assert "run_time_sec" not in user_msg


def test_chat_widget_omits_run_time_when_the_run_was_never_timed(db_fixtures):
    sr, _ = _make_sr_with_thread(uid="user-a", title="prior")

    request_body, _ = chat_widget_input_to_request_body(
        sr,
        {
            "input_prompt": "hello",
            "raw_input_text": "hello",
            "raw_output_text": ["reply"],
        },
        {"input_prompt": "follow up"},
    )

    assert "run_time_sec" not in request_body["messages"][1]


def test_get_chat_widget_messages_exports_run_time_on_assistant_messages():
    """Only the response carries a run time - the outgoing half has none."""
    messages = get_chat_widget_messages(
        {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "reply", "run_time_sec": 3.5},
            ],
            "input_prompt": "latest question",
            "output_text": ["latest reply"],
            "__run_time": 1.25,
        }
    )

    assert "run_time_sec" not in messages[0]
    assert messages[1]["run_time_sec"] == 3.5
    # the live turn reports the run currently being viewed
    assert messages[3]["run_time_sec"] == 1.25


def test_get_chat_widget_messages_omits_run_time_while_still_running():
    """A run has no time until it finishes, so nothing shows mid-answer."""
    messages = get_chat_widget_messages(
        {"input_prompt": "hello", "__run_status": "Running..."}
    )

    assert messages[1]["type"] == "message_part"
    assert messages[1]["run_time_sec"] is None


def test_run_time_is_stripped_before_reaching_the_llm():
    from daras_ai_v2.language_model_body import to_llm_body

    body = to_llm_body([{"role": "assistant", "content": "reply", "run_time_sec": 3.5}])

    assert "run_time_sec" not in body[0]


def test_created_at_is_stripped_before_reaching_the_llm():
    from daras_ai_v2.language_model_body import to_llm_body

    body = to_llm_body(
        [
            {
                "role": "user",
                "content": "hello",
                "created_at": "2026-08-13T10:30:00+00:00",
            }
        ]
    )

    assert "created_at" not in body[0]


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


def _make_sr(*, uid: str, run_id: str, state: dict) -> SavedRun:
    return SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id=run_id,
        uid=uid,
        state=state,
    )


def _make_thread_run(
    thread: MessageThread, *, run_id: str, uid: str, prompt: str
) -> SavedRun:
    """A later turn in `thread`, becoming its last_run."""
    sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id=run_id,
        uid=uid,
        message_thread=thread,
        state={"input_prompt": prompt, "raw_input_text": prompt},
    )
    thread.last_run = sr
    thread.save(update_fields=["last_run"])
    return sr


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
