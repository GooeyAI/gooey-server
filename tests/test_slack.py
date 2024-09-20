import pytest
from decouple import config
from starlette.testclient import TestClient

from bots.models import Message, SavedRun, BotIntegration, Conversation, Platform
from daras_ai_v2.slack_bot import safe_channel_name
from recipes.VideoBots import VideoBotsPage
from server import app


def test_slack_safe_channel_name():
    assert safe_channel_name("hello world!") == "hello-world"
    assert safe_channel_name("My, Awesome, Channel %") == "my-awesome-channel"


@pytest.mark.skipif(
    not config("TEST_SLACK_TEAM_ID", None), reason="No test slack team id"
)
def test_slack_get_response_for_msg_id(transactional_db):
    team_id = config("TEST_SLACK_TEAM_ID")
    user_id = config("TEST_SLACK_USER_ID")
    auth_token = config("TEST_SLACK_AUTH_TOKEN")

    convo = Conversation.objects.create(
        bot_integration=BotIntegration.objects.create(
            platform=Platform.SLACK,
        ),
        slack_team_id=team_id,
        slack_user_id=user_id,
    )
    incoming_msg = Message.objects.create(
        conversation=convo,
        platform_msg_id="incoming-msg",
    )
    Message.objects.create(
        conversation=convo,
        platform_msg_id="response-msg",
        saved_run=SavedRun.objects.create(
            state=VideoBotsPage.ResponseModel(
                raw_tts_text=["hello, world!"],
                output_text=["hello, world! [2]"],
                final_prompt="",
                output_audio=[],
                output_video=[],
                references=[],
            ).dict(),
        ),
    )

    client = TestClient(app)
    r = client.get(
        f"/__/slack/get-response-for-msg/{incoming_msg.platform_msg_id}/",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    assert r.json().get("content") == "hello, world!"
