import requests
from furl import furl
from urllib.parse import parse_qs
from string import Template
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from starlette.background import BackgroundTasks
from starlette.responses import RedirectResponse, HTMLResponse

from langcodes import Language

from bots.models import BotIntegration, Platform
from daras_ai_v2 import settings
from daras_ai_v2.bots import _on_msg, request_json, request_body

from daras_ai_v2.slack_bot import SlackBot
from daras_ai_v2.asr import run_google_translate

router = APIRouter()

slack_connect_url = "https://slack.com/oauth/v2/authorize?client_id=5628699523239.5666992444400&scope=app_mentions:read,incoming-webhook,channels:read,chat:write&user_scope="

SLACK_CONFIRMATION_MSG = """
Hi there! 👋

$name is now connected to your Slack workspace in this channel! 

@mention me and I'll respond to you in this channel. Add 👍 or 👎 to my responses to help me learn.

I have been configured for $user_language and will respond to you in that language.

Type `/help` to see what I can do for you.
""".strip()

SLACK_HELP_MSG = "@mention me and I'll respond to you in this channel. Add 👍 or 👎 to my responses to help me learn. I'll respond to text, audio and video messages!"


@router.get("/__/slack/redirect/")
def slack_connect_redirect(request: Request):
    print(request)
    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    retry_button = f'<a href="{slack_connect_url}">Retry</a>'

    code = request.query_params.get("code")
    if not code:
        return HTMLResponse(
            f"<p>Oh No! Something went wrong here.</p><p>Error: {dict(request.query_params)}</p>"
            + retry_button,
            status_code=400,
        )
    res = requests.post(
        f"https://slack.com/api/oauth.v2.access?code={code}&client_id={settings.SLACK_CLIENT_ID}&client_secret={settings.SLACK_CLIENT_SECRET}",  # TODO: use Basic auth header instead
    )
    print(res.text)
    res = res.json()
    slack_access_token = res["access_token"]
    slack_workspace = res["team"]["name"]
    slack_channel = res["incoming_webhook"]["channel"]
    slack_channel_id = res["incoming_webhook"]["channel_id"]
    slack_channel_hook_url = res["incoming_webhook"]["url"]

    try:
        bi = BotIntegration.objects.get(
            slack_access_token=slack_access_token, slack_channel_id=slack_channel_id
        )
    except BotIntegration.DoesNotExist:
        bi = BotIntegration(
            slack_access_token=slack_access_token,
            slack_channel_id=slack_channel_id,
            slack_channel_hook_url=slack_channel_hook_url,
            billing_account_uid=request.user.uid,
            name=slack_workspace + " - " + slack_channel,
            platform=Platform.SLACK,
        )
        bi.save()

    send_confirmation_msg(bi)

    return HTMLResponse(
        f"Sucessfully Connected to {slack_workspace} workspace on {slack_channel}! You may now close this page."
    )


def send_confirmation_msg(bot: BotIntegration):
    substitutions = vars(bot).copy()  # convert to dict for string substitution
    substitutions["user_language"] = Language.get(
        bot.user_language, "en"
    ).display_name()
    text = run_google_translate(
        [Template(SLACK_CONFIRMATION_MSG).safe_substitute(**substitutions)],
        target_language=bot.user_language,
        source_language="en",
    )[0]
    requests.post(
        bot.slack_channel_hook_url,
        data=('{"text": "' + text + '"}').encode("utf-8"),
        headers={"Content-type": "application/json"},
    )


@router.post("/__/slack/event/")
def slack_event(
    background_tasks: BackgroundTasks,
    data: dict = Depends(request_json),
):
    if data["token"] != settings.SLACK_VERIFICATION_TOKEN:
        raise HTTPException(403, "Only accepts requests from Slack")
    if data["type"] == "url_verification":
        return data["challenge"]
    print("slack_eventhook: " + str(data))
    if data["type"] == "event_callback":
        workspace_id = data["team_id"]
        application_id = data["api_app_id"]
        event = data["event"]
    if event["type"] == "app_mention":
        bot = SlackBot(
            {
                "workspace_id": workspace_id,
                "application_id": application_id,
                "channel": event["channel"],
                "thread_ts": event["event_ts"],
                "text": event["text"],
                "user": event["user"],
            }
        )
        background_tasks.add_task(_on_msg, bot)
    return Response("OK")


@router.post("/__/slack/help/")
def slack_help(data: dict = Depends(request_body)):
    params = parse_qs(data)
    try:
        bi = BotIntegration.objects.get(slack_channel_id=params["channel_id"])
        language = bi.user_language
    except BotIntegration.DoesNotExist:
        language = "en"
    try:
        return run_google_translate(
            [Template(SLACK_HELP_MSG).safe_substitute(**params)],
            target_language=params.get("text", [language])[0],
            source_language="en",
        )[0]
    except requests.exceptions.HTTPError:
        return Response(
            "Unsupported language code! Try running `/help en` to ensure the language is supported."
        )
