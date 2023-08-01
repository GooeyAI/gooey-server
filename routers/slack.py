import requests
from furl import furl
import json

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from starlette.background import BackgroundTasks
from starlette.responses import RedirectResponse, HTMLResponse

from bots.models import BotIntegration, Platform
from daras_ai_v2 import settings
from daras_ai_v2.bots import _on_msg, request_json, request_urlencoded_body

from daras_ai_v2.slack_bot import SlackBot

router = APIRouter()

slack_connect_url = f"https://slack.com/oauth/v2/authorize?client_id={settings.SLACK_CLIENT_ID}&scope=channels:history,channels:read,chat:write,chat:write.customize,files:read,incoming-webhook&user_scope="


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
            show_feedback_buttons=True,
        )
        bi.save()

    return HTMLResponse(
        f"Sucessfully Connected to {slack_workspace} workspace on {slack_channel}! You may now close this page."
    )


@router.post("/__/slack/interaction/")
def slack_interaction(
    background_tasks: BackgroundTasks,
    data: dict = Depends(request_urlencoded_body),
):
    print("slack_interaction: " + str(data))
    data = json.loads(data["payload"][0])
    if data["token"] != settings.SLACK_VERIFICATION_TOKEN:
        raise HTTPException(403, "Only accepts requests from Slack")
    if data["type"] == "block_actions":
        workspace_id = data["team"]["id"]
        application_id = data["api_app_id"]
        bot = SlackBot(
            {
                "workspace_id": workspace_id,
                "application_id": application_id,
                "channel": data["channel"]["id"],
                "thread_ts": data["container"]["thread_ts"],
                "text": "",
                "user": data["user"]["id"],
                "files": [],
                "actions": data["actions"],
            }
        )
        background_tasks.add_task(_on_msg, bot)


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
    if event["type"] == "message":
        if event.get("subtype", "text") not in ["text", "slack_audio", "file_share"]:
            print("ignoring message subtype: " + event.get("subtype"))
            return Response("OK")  # ignore messages from bots, and service messages
        try:
            bot = SlackBot(
                {
                    "workspace_id": workspace_id,
                    "application_id": application_id,
                    "channel": event["channel"],
                    "thread_ts": event["event_ts"],
                    "text": event.get("text", ""),
                    "user": event["user"],
                    "files": event.get("files", []),
                    "actions": [],
                }
            )
        except BotIntegration.DoesNotExist:
            print("contacted from an invalid channel, ignore message")
            return Response("OK")  # contacted from an invalid channel, ignore message
        background_tasks.add_task(_on_msg, bot)
    return Response("OK")
