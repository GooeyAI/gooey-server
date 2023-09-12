import requests
from furl import furl
import json

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from requests.auth import HTTPBasicAuth
from sentry_sdk import capture_exception
from starlette.background import BackgroundTasks
from starlette.responses import RedirectResponse, HTMLResponse

from bots.models import BotIntegration, Platform
from daras_ai_v2 import settings
from daras_ai_v2.bots import _on_msg, request_json, request_urlencoded_body

from daras_ai_v2.slack_bot import SlackBot, SlackMessage, invite_bot_account_to_channel
from django.db import transaction

router = APIRouter()

slack_connect_url = furl(
    "https://slack.com/oauth/v2/authorize",
    query_params=dict(
        client_id=settings.SLACK_CLIENT_ID,
        scope=",".join(
            [
                "channels:history",
                "channels:read",
                "chat:write",
                "chat:write.customize",
                "files:read",
                "files:write",
                "groups:history",
                "groups:read",
                "groups:write",
                "incoming-webhook",
                "remote_files:read",
                "remote_files:share",
                "remote_files:write",
                "im:history",
                "im:read",
                "im:write",
            ]
        ),
        user_scope=",".join(
            [
                "channels:write",
                "channels:write.invites",
                "groups:write",
                "groups:write.invites",
                # "chat:write",
            ]
        ),
    ),
)


@router.get("/__/slack/redirect/")
def slack_connect_redirect(request: Request):
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
        furl(
            "https://slack.com/api/oauth.v2.access",
            query_params=dict(code=code),
        ).url,
        auth=HTTPBasicAuth(settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET),
    )
    res.raise_for_status()
    print(res.text)
    res = res.json()
    slack_access_token = res["access_token"]
    slack_workspace = res["team"]["name"]
    slack_channel = res["incoming_webhook"]["channel"]
    slack_channel_id = res["incoming_webhook"]["channel_id"]
    slack_channel_hook_url = res["incoming_webhook"]["url"]
    slack_bot_user_id = res["bot_user_id"]
    slack_user_access_token = res["authed_user"]["access_token"]
    slack_team_id = res["team"]["id"]

    invite_bot_account_to_channel(
        slack_channel_id, slack_bot_user_id, slack_user_access_token
    )

    config = dict(
        slack_access_token=slack_access_token,
        slack_channel_hook_url=slack_channel_hook_url,
        billing_account_uid=request.user.uid,
        slack_team_id=slack_team_id,
    )

    with transaction.atomic():
        bi, created = BotIntegration.objects.get_or_create(
            slack_channel_id=slack_channel_id,
            defaults=dict(
                **config,
                name=slack_workspace + " - " + slack_channel,
                platform=Platform.SLACK,
                show_feedback_buttons=True,
            ),
        )
        if not created:
            BotIntegration.objects.filter(pk=bi.pk).update(**config)

    return HTMLResponse(
        f"Sucessfully Connected to {slack_workspace} workspace on {slack_channel}! You may now close this page."
    )


@router.post("/__/slack/interaction/")
def slack_interaction(
    background_tasks: BackgroundTasks,
    data: dict = Depends(request_urlencoded_body),
):
    data = json.loads(data.get("payload", ["{}"])[0])
    print("slack_interaction: " + str(data))
    if not data:
        raise HTTPException(400, "No payload")
    if data["token"] != settings.SLACK_VERIFICATION_TOKEN:
        raise HTTPException(403, "Only accepts requests from Slack")
    if data["type"] == "block_actions":
        workspace_id = data["team"]["id"]
        application_id = data["api_app_id"]
        bot = SlackBot(
            SlackMessage(
                workspace_id=workspace_id,
                application_id=application_id,
                channel=data["channel"]["id"],
                thread_ts=data["container"]["thread_ts"],
                text="",
                user=data["user"]["id"],
                files=[],
                actions=data["actions"],
                msg_id=data["container"]["message_ts"],
                team_id=data["team"]["id"],
            )
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
            if event.get("subtype", "text") not in [
                "text",
                "slack_audio",
                "file_share",
            ]:
                print("ignoring message subtype: " + event.get("subtype"))
                return Response("OK")  # ignore messages from bots, and service messages
            try:
                bot = SlackBot(
                    SlackMessage(
                        workspace_id=workspace_id,
                        application_id=application_id,
                        channel=event["channel"],
                        thread_ts=event["event_ts"],
                        text=event.get("text", ""),
                        user=event["user"],
                        files=event.get("files", []),
                        actions=[],
                        msg_id=event["ts"],
                        team_id=event["team"],
                    )
                )
            except BotIntegration.DoesNotExist as e:
                capture_exception(e)
                print("contacted from an un-monitored channel, ignoring:", e)
                return Response(
                    "OK"
                )  # contacted from a channel that this integration has not been explicitly connected to (we recieve events from all channels in WorkSpace), ignore message
            background_tasks.add_task(_on_msg, bot)
    return Response("OK")


@router.get("/__/slack/redirect/shortcuts/")
def slack_connect_redirect_shortcuts(request: Request):
    retry_button = f'<a href="{slack_connect_url}">Retry</a>'

    code = request.query_params.get("code")
    if not code:
        return HTMLResponse(
            f"<p>Oh No! Something went wrong here.</p><p>Error: {dict(request.query_params)}</p>"
            + retry_button,
            status_code=400,
        )
    res = requests.post(
        furl(
            "https://slack.com/api/oauth.v2.access",
            query_params=dict(code=code, redirect_uri=slack_shortcuts_redirect_uri),
        ).url,
        auth=HTTPBasicAuth(settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET),
    )
    res.raise_for_status()
    print(res.text)
    res = res.json()
    payload = json.dumps(
        dict(
            slack_channel=res["incoming_webhook"]["channel"].strip("#"),
            slack_channel_id=res["incoming_webhook"]["channel_id"],
            slack_user_access_token=res["authed_user"]["access_token"],
            slack_team_id=res["team"]["id"],
        ),
        indent=2,
    )
    return HTMLResponse(
        # language=HTML
        """
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-size: 1.2rem; text-align: center; font-family: sans-serif">
            <p>
                <textarea style="font-family: monospace; width: 100%%;" rows=5 id="foo">%(payload)s</textarea>
            </p>

            <p>
                <button id="new-copy" style="padding: 2rem; font-size: 1.5rem;">
                    Click here to Complete Setup
                </button>
            </p>

            <script>
                document.getElementById("new-copy").addEventListener("click", event => {
                    navigator.clipboard.writeText(%(payload)r);
                    document.body.innerText = "Setup Complete! You can close this window now."
                });
            </script>
        </body>
        """
        % dict(payload=payload)
    )


slack_shortcuts_redirect_uri = (
    furl(settings.APP_BASE_URL)
    / router.url_path_for(slack_connect_redirect_shortcuts.__name__)
).url
