import json
from unittest.mock import Mock

import pytest
import requests

from bots.models import BotIntegration
from daras_ai_v2 import bots, facebook_bots
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.facebook_bots import WhatsappBot


@pytest.mark.parametrize(
    "text,media,types",
    [
        ("Answer", {}, ["list"]),
        ("Answer", {"audio": ["https://example.com/audio.mp3"]}, ["list", "audio"]),
        ("Answer<button>Follow up</button>", {}, ["button", "list"]),
        (
            "Answer<select>" + "<option>A</option>" * 7 + "</select>",
            {},
            ["list"],
        ),
        (
            "Answer<select>" + "<option>A</option>" * 8 + "</select>",
            {},
            ["list", "list"],
        ),
        (
            "Answer<select>" + "<option>A</option>" * 11 + "</select>",
            {"audio": ["https://example.com/audio.mp3"]},
            ["list", "list", "audio", "list"],
        ),
        (None, {}, ["list"]),
    ],
)
def test_whatsapp_utilities_are_one_options_group(wa_sender, text, media, types):
    bot, sent = wa_sender

    bot.send_msg(text=text, send_feedback_buttons=True, **media)

    assert [
        msg.get("interactive", {}).get("type", msg["type"]) for msg in sent
    ] == types
    assert_utility_group(sent)


def test_disabled_feedback_only_keeps_new_option(wa_sender):
    bot, sent = wa_sender

    bot.send_msg(
        text='Answer<select gui-action="disable_feedback"><option>A</option></select>',
        send_feedback_buttons=True,
    )

    assert utility_ids(sent) == [bots.ButtonIds.new_conversation]


def test_whatsapp_utilities_can_be_deferred(wa_sender):
    bot, sent = wa_sender

    bot.send_msg(
        text="Partial response",
        send_feedback_buttons=True,
        send_utility_buttons=False,
    )

    assert len(sent) == 1
    assert sent[0]["type"] == "text"
    assert sent[0]["text"]["body"].strip() == "Partial response"
    assert "interactive" not in sent[0]


@pytest.mark.parametrize("reply_type", ["button_reply", "list_reply"])
def test_interactive_reply_uses_message_type(reply_type):
    bot = WhatsappBot.__new__(WhatsappBot)
    bot.input_message = {
        "interactive": {
            "type": reply_type,
            reply_type: {"id": "reply-1", "title": "Reply"},
        },
        "context": {"id": "context-1"},
    }

    reply = bot.get_interactive_msg_info()

    assert reply.button_id == "reply-1"
    assert reply.button_title == "Reply"
    assert reply.context_msg_id == "context-1"


def test_initialization_error_is_sent_without_utilities(monkeypatch):
    sent = []

    def fail_lookup(*args, **kwargs):
        raise UserError("Integration error")

    monkeypatch.setattr(WhatsappBot, "lookup_bot_integration", fail_lookup)
    monkeypatch.setattr(
        WhatsappBot, "_send_msg", lambda self, **kwargs: sent.append(kwargs)
    )

    with pytest.raises(UserError, match="Integration error"):
        WhatsappBot(
            message={"id": "msg-1", "from": "123", "type": "text"},
            metadata={"phone_number_id": "bot-1"},
        )

    assert sent == [{"text": "Integration error"}]


def test_reset_confirmation_is_sent_without_utilities():
    bot = Mock()
    bot.bi.new_conversation_button_text = ""

    bots.reset_convo(bot)

    bot.send_msg.assert_called_once_with(
        text=bots.RESET_MSG,
        should_translate=True,
        send_utility_buttons=False,
    )


def assert_utility_group(sent):
    expected = {
        bots.ButtonIds.new_conversation,
        bots.ButtonIds.feedback_thumbs_up,
        bots.ButtonIds.feedback_thumbs_down,
    }
    groups = []
    for msg in sent:
        action = msg.get("interactive", {}).get("action", {})
        rows = [
            row for section in action.get("sections", []) for row in section["rows"]
        ]
        ids = {row["id"] for row in rows}
        if ids & expected:
            assert expected <= ids
            groups.append(msg)
        assert not any(
            button["reply"]["id"] in expected for button in action.get("buttons", [])
        )
    assert len(groups) == 1


def utility_ids(sent):
    expected = {
        bots.ButtonIds.new_conversation,
        bots.ButtonIds.feedback_thumbs_up,
        bots.ButtonIds.feedback_thumbs_down,
    }
    return [
        row["id"]
        for msg in sent
        for section in msg.get("interactive", {}).get("action", {}).get("sections", [])
        for row in section["rows"]
        if row["id"] in expected
    ]


@pytest.fixture
def wa_sender(monkeypatch):
    bot = WhatsappBot.__new__(WhatsappBot)
    bot.bot_id = "test-bot"
    bot.user_id = "test-user"
    bot.access_token = "test-token"
    bot.bi = BotIntegration()
    bot.show_new_conversation_button = bot.bi.show_new_conversation_button
    sent = []

    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        response = requests.Response()
        response.status_code = 200
        response.reason = "OK"
        response._content = json.dumps(
            {"messages": [{"id": f"msg-{len(sent)}"}]}
        ).encode()
        return response

    monkeypatch.setattr(facebook_bots.requests, "post", post)
    return bot, sent
