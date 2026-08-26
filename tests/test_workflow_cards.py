import pytest

from bots.models import Conversation, MessageThread, SavedRun
from bots.models.bot_integration import Platform
from widgets.workflow_cards import mask_user_id, sender_from_run


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
