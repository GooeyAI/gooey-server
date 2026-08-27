import datetime

import pytest
from django.utils import timezone

from bots.models import Conversation, MessageThread, SavedRun
from bots.models.bot_integration import Platform
from widgets.workflow_cards import (
    RUN_STALE_AFTER,
    _run_title,
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
    assert mask_user_id("  padded  ") == "padded"


def _run(platform: Platform | None, convo: Conversation | None = None) -> SavedRun:
    return SavedRun(
        platform=platform,
        message_thread=MessageThread(bot_conversation=convo) if convo else None,
    )


@pytest.mark.parametrize(
    "platform,convo_kwargs,expected",
    [
        (Platform.WHATSAPP, dict(wa_phone_number="+919812348811"), "+91xxx8811"),
        (Platform.TELEGRAM, dict(telegram_user_name="seanb"), "@seanb"),
        (Platform.SLACK, dict(slack_user_name="seanbianchi"), "@seaxxxnchi"),
        (
            Platform.WEB,
            dict(web_user_id="3be8a5da-d476-4924-9e45-f4aa831ac076"),
            "3bexxxc076",
        ),
        # no display name to fall back on, so the raw id carries the row
        (Platform.SLACK, dict(slack_user_id="U01ABCD9876"), "U01xxx9876"),
    ],
)
def test_sender_label_per_platform(platform, convo_kwargs, expected):
    sender = sender_from_run(_run(platform, Conversation(**convo_kwargs)))
    assert sender.label == expected
    assert sender.icon == platform.get_icon()


def test_sender_is_none_without_a_platform():
    assert sender_from_run(_run(None)) is None


def test_unknown_platform_does_not_blow_up_the_card():
    # a run recorded by a deploy that knows a platform this one doesn't
    assert sender_from_run(_run(999)) is None


def test_sender_survives_a_missing_conversation():
    # the icon still says where the run came from
    sender = sender_from_run(_run(Platform.WHATSAPP))
    assert sender.label == ""
    assert sender.icon == Platform.WHATSAPP.get_icon()


def _status_run(**kwargs) -> SavedRun:
    kwargs.setdefault("updated_at", timezone.now())
    return SavedRun(**kwargs)


def test_no_badge_on_a_finished_run():
    assert (
        run_status_from_run(_status_run(run_time=datetime.timedelta(seconds=3))) is None
    )


def test_no_badge_on_a_run_that_never_started():
    assert run_status_from_run(_status_run()) is None


def test_running_badge_carries_the_worker_status():
    status = run_status_from_run(_status_run(run_status="Calling with Gemini..."))
    assert status.state == "running"
    assert status.label == "Calling with Gemini..."


def test_starting_is_its_own_state():
    assert (
        run_status_from_run(_status_run(run_status="Starting...")).state == "starting"
    )


def test_a_worker_that_stopped_reporting_is_not_still_running():
    # otherwise a dead run spins on the card forever
    stale = timezone.now() - RUN_STALE_AFTER - datetime.timedelta(minutes=1)
    status = run_status_from_run(_status_run(run_status="Working...", updated_at=stale))
    assert status.state == "failed"
    assert status.label == "Timed out"


def test_an_error_outranks_a_leftover_status():
    status = run_status_from_run(_status_run(run_status="Working...", error_msg="boom"))
    assert status.state == "failed"


def test_a_cancel_outranks_everything():
    status = run_status_from_run(
        _status_run(run_status="Working...", error_msg="boom", is_cancelled=True)
    )
    assert status.state == "cancelled"


@pytest.mark.parametrize(
    "surface,expected",
    [
        (SavedRun.Surface.run, "Run: School Meal Advisor"),
        (SavedRun.Surface.deployment, "Deployment: School Meal Advisor"),
        (SavedRun.Surface.api, "API: School Meal Advisor"),
    ],
)
def test_title_names_the_surface(surface, expected):
    assert _run_title(SavedRun(surface=surface), "School Meal Advisor") == expected


def test_title_survives_an_unknown_surface():
    assert _run_title(SavedRun(surface=999), "School Meal Advisor") == (
        "School Meal Advisor"
    )
