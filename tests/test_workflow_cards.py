import datetime

from django.utils import timezone

from bots.models import Conversation, MessageThread, SavedRun
from bots.models.bot_integration import Platform
from widgets.workflow_cards import (
    RUN_STALE_AFTER,
    mask_user_id,
    run_status_from_run,
    sender_from_run,
)


def test_mask_user_id_keeps_the_ends():
    assert mask_user_id("+91 98123 48811") == "+91xxx8811"
    assert mask_user_id("3be8a5da-d476-4924-9e45-f4aa831ac076") == "3bexxxc076"


def test_mask_user_id_leaves_short_values_alone():
    # a mask here would cost more than it hides
    assert mask_user_id("seanb") == "seanb"
    assert mask_user_id("") == ""


def _run(platform, convo: Conversation | None = None) -> SavedRun:
    return SavedRun(
        platform=platform,
        message_thread=MessageThread(bot_conversation=convo) if convo else None,
    )


def test_sender_names_the_conversation_and_its_platform():
    sender = sender_from_run(
        _run(Platform.WHATSAPP, Conversation(wa_phone_number="+919812348811"))
    )

    assert sender.label == "+91xxx8811"
    assert sender.icon == Platform.WHATSAPP.get_icon()


def test_sender_falls_back_to_the_icon_alone():
    # no platform at all, an unknown one, and a run whose conversation is gone
    assert sender_from_run(_run(None)) is None
    assert sender_from_run(_run(999)) is None
    assert sender_from_run(_run(Platform.WHATSAPP)).label == ""


def _status_run(**kwargs) -> SavedRun:
    kwargs.setdefault("updated_at", timezone.now())
    return SavedRun(**kwargs)


def test_no_badge_on_a_finished_run():
    assert (
        run_status_from_run(_status_run(run_time=datetime.timedelta(seconds=3))) is None
    )


def test_running_badge_carries_the_worker_status():
    status = run_status_from_run(_status_run(run_status="Calling with Gemini..."))

    assert status.state == "running"
    assert status.label == "Calling with Gemini..."


def test_a_worker_that_stopped_reporting_is_not_still_running():
    # otherwise a dead run spins on the card forever
    stale = timezone.now() - RUN_STALE_AFTER - datetime.timedelta(minutes=1)
    status = run_status_from_run(_status_run(run_status="Working...", updated_at=stale))

    assert status.state == "failed"
    assert status.label == "Timed out"


def test_a_cancel_outranks_an_error_which_outranks_a_leftover_status():
    assert (
        run_status_from_run(
            _status_run(run_status="Working...", error_msg="boom", is_cancelled=True)
        ).state
        == "cancelled"
    )
    assert (
        run_status_from_run(
            _status_run(run_status="Working...", error_msg="boom")
        ).state
        == "failed"
    )
