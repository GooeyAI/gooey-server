from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bots.models import Platform, SavedRun, Workflow
from bots.models.message_thread import MessageThread
from daras_ai_v2.bots import (
    _cancel_active_run_and_merge_inputs,
    _merge_run_inputs,
    _submit_bot_run,
)


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (
            {"input_images": ["image-1"]},
            {"input_images": ["image-2"]},
            {"input_images": ["image-1", "image-2"]},
        ),
        (
            {"input_documents": ["document-1"]},
            {"input_documents": ["document-2"]},
            {"input_documents": ["document-1", "document-2"]},
        ),
        (
            {"input_prompt": "first caption"},
            {"input_prompt": "second caption"},
            {"input_prompt": "first caption\nsecond caption"},
        ),
        (
            {"input_audio": "audio-1"},
            {"input_audio": "audio-2", "input_images": ["image-1"]},
            {"input_audio": "audio-2", "input_images": ["image-1"]},
        ),
        (
            {"selected_model": "gpt_4o"},
            {"input_images": ["image-1"]},
            {"selected_model": "gpt_4o", "input_images": ["image-1"]},
        ),
    ],
)
def test_merge_run_inputs(previous, current, expected):
    merged = _merge_run_inputs(previous, current)

    for field, value in expected.items():
        assert merged[field] == value


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("run_status", "is_cancelled"), [("", False), ("Running...", True)]
)
def test_new_whatsapp_event_does_not_merge_inactive_run(run_status, is_cancelled):
    run, thread = _make_thread(run_status=run_status, is_cancelled=is_cancelled)
    current = {"input_images": ["image-2"]}

    request_body = _cancel_active_run_and_merge_inputs(thread, current)

    run.refresh_from_db()
    assert run.is_cancelled is is_cancelled
    assert request_body is current


@pytest.mark.django_db
def test_submit_bot_run_replaces_active_run_and_ignores_duplicate_event():
    active_run, thread = _make_thread(run_status="Running...")
    bot = SimpleNamespace(
        platform=Platform.WHATSAPP,
        user_msg_id="event-2",
        page_cls=None,
        query_params={},
        workspace=None,
        current_user=None,
    )
    celery_result = object()

    def submit_api_call(**kwargs):
        replacement = SavedRun.objects.create(
            workflow=Workflow.VIDEO_BOTS,
            run_status="Running...",
            state=kwargs["request_body"],
            message_thread=thread,
        )
        thread.last_run = replacement
        thread.save(update_fields=["last_run"])
        return celery_result, replacement

    with (
        patch("daras_ai_v2.bots.redis_lock", return_value=nullcontext()) as lock,
        patch(
            "daras_ai_v2.bots.submit_api_call", side_effect=submit_api_call
        ) as submit,
    ):
        result, replacement = _submit_bot_run(
            bot=bot,
            request_body={"input_images": ["image-2"]},
            message_thread=thread,
        )
        duplicate = _submit_bot_run(
            bot=bot,
            request_body={"input_images": ["image-2"]},
            message_thread=thread,
        )

    active_run.refresh_from_db()
    replacement.refresh_from_db()
    thread.refresh_from_db()
    assert result is celery_result
    assert active_run.is_cancelled is True
    assert replacement.state["input_images"] == ["image-1", "image-2"]
    assert replacement.user_message_id == "event-2"
    assert replacement.is_cancelled is False
    assert thread.last_run == replacement
    assert duplicate is None
    assert submit.call_count == 1
    assert lock.call_count == 2


def test_submit_bot_run_does_not_coordinate_non_whatsapp_events():
    bot = SimpleNamespace(
        platform=Platform.SLACK,
        page_cls=None,
        query_params={},
        workspace=None,
        current_user=None,
    )
    request_body = {"input_images": ["image-2"]}
    expected = (object(), object())

    with (
        patch("daras_ai_v2.bots.redis_lock") as lock,
        patch("daras_ai_v2.bots.submit_api_call", return_value=expected) as submit,
    ):
        result = _submit_bot_run(
            bot=bot,
            request_body=request_body,
            message_thread=SimpleNamespace(),
        )

    assert result == expected
    assert submit.call_args.kwargs["request_body"] is request_body
    lock.assert_not_called()


def _make_thread(
    *, run_status: str, is_cancelled: bool = False
) -> tuple[SavedRun, MessageThread]:
    run = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_status=run_status,
        is_cancelled=is_cancelled,
        state={"input_images": ["image-1"]},
    )
    thread = MessageThread.objects.create(first_run=run, last_run=run)
    run.message_thread = thread
    run.save(update_fields=["message_thread"])
    return run, thread
