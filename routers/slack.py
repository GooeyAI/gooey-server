# import traceback

# import glom
# from daras_ai_v2.bots import (
#     BotInterface,
#     PAGE_NOT_CONNECTED_ERROR,
#     RESET_KEYWORD,
#     RESET_MSG,
#     DEFAULT_RESPONSE,
#     INVALID_INPUT_FORMAT,
#     AUDIO_ASR_CONFIRMATION,
#     ERROR_MSG,
#     FEEDBACK_THUMBS_UP_MSG,
#     FEEDBACK_THUMBS_DOWN_MSG,
#     FEEDBACK_CONFIRMED_MSG,
#     TAPPED_SKIP_MSG,
#     # Mock testing
#     # _echo,
#     # _mock_api_output,
# )
import requests

# from fastapi import APIRouter, HTTPException, Depends
# from fastapi.responses import RedirectResponse
# from furl import furl
# from sentry_sdk import capture_exception
# from starlette.background import BackgroundTasks
# from starlette.requests import Request
# from starlette.responses import HTMLResponse, Response

# from app_users.models import AppUser
# from bots.models import (
#     BotIntegration,
#     Platform,
#     Message,
#     Conversation,
#     Feedback,
#     SavedRun,
#     ConvoState,
# )
# from daras_ai_v2 import settings, db
# from daras_ai_v2.all_pages import Workflow
# from daras_ai_v2.asr import AsrModels, run_google_translate
# from daras_ai_v2.facebook_bots import WhatsappBot, FacebookBot
# from daras_ai_v2.functional import map_parallel
# from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISSTANT
# from gooeysite.bg_db_conn import db_middleware

# router = APIRouter()


def run_google_translate(text: str, language: str) -> str:
    return text


SLACK_CONFIRMATION_MSG = """
Hi there! 👋

{name} is now connected to your Slack workspace! 

I was created to {slack_description} You can DM me to start a conversation with me ({name}). 

I'm also available in this channel if you have any questions regarding how I work or need to update one of my settings.

I have been configured for {user_language} and will respond to you in that language.

Type `/help` to see what I can do for you.
""".strip()


def send_confirmation_msg(bot: "BotIntegration"):
    requests.post(
        "https://hooks.slack.com/services/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",
        data=f'{"text": "{run_google_translate(SLACK_CONFIRMATION_MSG.format(**vars(bot)), bot.user_language)}"}',
        headers={"Content-type": "application/json"},
    )


class Test:
    def __init__(self):
        self.name = "test_name"
        self.slack_description = "test_description"
        self.user_language = "en"


send_confirmation_msg(Test())
