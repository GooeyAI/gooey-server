import json

import requests
from django.db import transaction
from fastapi import APIRouter, HTTPException, Depends, Request, Response, Header
from furl import furl
from requests import HTTPError
from requests.auth import HTTPBasicAuth
from sentry_sdk import capture_exception
from starlette.background import BackgroundTasks
from starlette.responses import RedirectResponse, HTMLResponse

from bots.models import BotIntegration, Platform, Conversation, Message
from bots.tasks import create_personal_channels_for_all_members
from daras_ai_v2 import settings
from daras_ai_v2.bots import _on_msg, request_json, request_urlencoded_body
from daras_ai_v2.search_ref import parse_refs
from daras_ai_v2.slack_bot import (
    SlackBot,
    invite_bot_account_to_channel,
    create_personal_channel,
    SlackAPIError,
    fetch_user_info,
    parse_slack_response,
)
from gooey_token_authentication1.token_authentication import auth_keyword
from recipes.VideoBots import VideoBotsPage

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
                "groups:write.invites",
                "groups:write.topic",
                "incoming-webhook",
                "remote_files:read",
                "remote_files:share",
                "remote_files:write",
                "users:read",
            ]
        ),
        user_scope=",".join(
            [
                "channels:write",
                "channels:write.invites",
                "groups:write",
                "groups:write.invites",
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
    r = requests.post(
        furl(
            "https://slack.com/api/oauth.v2.access",
            query_params=dict(code=code),
        ).url,
        auth=HTTPBasicAuth(settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET),
    )
    r.raise_for_status()
    print("> slack_connect_redirect:", r.text)

    data = r.json()
    slack_access_token = data["access_token"]
    slack_team_id = data["team"]["id"]
    slack_team_name = data["team"]["name"]
    slack_channel_id = data["incoming_webhook"]["channel_id"]
    slack_channel_name = data["incoming_webhook"]["channel"].strip("#")
    slack_channel_hook_url = data["incoming_webhook"]["url"]
    slack_bot_user_id = data["bot_user_id"]
    slack_user_access_token = data["authed_user"]["access_token"]

    try:
        invite_bot_account_to_channel(
            slack_channel_id, slack_bot_user_id, slack_user_access_token
        )
    except SlackAPIError as e:
        capture_exception(e)
        return HTMLResponse(
            f"<p>Oh No! Something went wrong here.</p><p>{repr(e)}</p>" + retry_button,
            status_code=400,
        )

    config = dict(
        slack_access_token=slack_access_token,
        slack_channel_hook_url=slack_channel_hook_url,
        billing_account_uid=request.user.uid,
        slack_team_name=slack_team_name,
        slack_channel_name=slack_channel_name,
    )

    with transaction.atomic():
        bi, created = BotIntegration.objects.get_or_create(
            slack_channel_id=slack_channel_id,
            slack_team_id=slack_team_id,
            defaults=dict(
                **config,
                name=f"{slack_team_name} | #{slack_channel_name}",
                platform=Platform.SLACK,
                show_feedback_buttons=True,
            ),
        )
        if not created:
            BotIntegration.objects.filter(pk=bi.pk).update(**config)
            bi.refresh_from_db()

    if bi.slack_create_personal_channels:
        create_personal_channels_for_all_members.delay(bi.id)

    return HTMLResponse(
        f"Sucessfully Connected to {slack_team_name} workspace on #{slack_channel_name}! You may now close this page."
    )


@router.post("/__/slack/interaction/")
def slack_interaction(
    background_tasks: BackgroundTasks,
    data: dict = Depends(request_urlencoded_body),
):
    data = json.loads(data.get("payload", ["{}"])[0])
    print("> slack_interaction:", data)
    if not data:
        raise HTTPException(400, "No payload")
    if data["token"] != settings.SLACK_VERIFICATION_TOKEN:
        raise HTTPException(403, "Only accepts requests from Slack")
    if data["type"] != "block_actions":
        return
    bot = SlackBot(
        message_ts=data["container"]["message_ts"],
        team_id=data["team"]["id"],
        user_id=data["user"]["id"],
        channel_id=data["channel"]["id"],
        actions=data["actions"],
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
    print("> slack_event:", data)
    _handle_slack_event(data, background_tasks)
    return Response("OK")


def _handle_slack_event(event: dict, background_tasks: BackgroundTasks):
    if event["type"] != "event_callback":
        return
    message = event["event"]
    try:
        match message.get("type"):
            case "member_joined_channel":
                bi = BotIntegration.objects.get(
                    slack_channel_id=message["channel"],
                    slack_team_id=event["team"],
                )
                if not bi.slack_create_personal_channels:
                    return
                try:
                    user = fetch_user_info(message["user"], bi.slack_access_token)
                except SlackAPIError as e:
                    if e.error == "missing_scope":
                        print(f"Error: Missing scopes for - {message!r}")
                        capture_exception(e)
                    else:
                        raise
                else:
                    create_personal_channel(bi, user)

            case "message":
                # Ignore subtypes other than slack_audio and file_share. If there's no subtype, assume text
                subtype = message.get("subtype")
                if subtype and subtype not in ["slack_audio", "file_share"]:
                    return

                files = message.get("files", [])
                if not files:
                    message.get("message", {}).get("files", [])
                if not files:
                    attachments = message.get("attachments", [])
                    files = [
                        file
                        for attachment in attachments
                        for file in attachment.get("files", [])
                    ]
                bot = SlackBot(
                    message_ts=message["ts"],
                    team_id=message.get("team", event["team_id"]),
                    channel_id=message["channel"],
                    user_id=message["user"],
                    text=message.get("text", ""),
                    files=files,
                )
                background_tasks.add_task(_on_msg, bot)

    except BotIntegration.DoesNotExist as e:
        print(f"Error: contacted from an unknown channel - {e!r}")
        capture_exception(e)


@router.get("/__/slack/oauth/shortcuts/")
def slack_oauth_shortcuts():
    return RedirectResponse(str(slack_shortcuts_connect_url))


@router.get("/__/slack/redirect/shortcuts/")
def slack_connect_redirect_shortcuts(request: Request):
    retry_button = f'<a href="{slack_shortcuts_connect_url}">Retry</a>'

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
    res = res.json()
    print("> slack_connect_redirect_shortcuts:", res)

    channel_id = res["incoming_webhook"]["channel_id"]
    user_id = res["authed_user"]["id"]
    team_id = res["team"]["id"]
    access_token = res["authed_user"]["access_token"]

    try:
        convo = Conversation.objects.get(
            slack_channel_id=channel_id, slack_user_id=user_id, slack_team_id=team_id
        )
    except Conversation.DoesNotExist:
        return HTMLResponse(
            "<p>Oh No! Something went wrong here.</p>"
            "<p>Conversation not found. Please make sure this channel is connected to the gooey bot</p>"
            + retry_button,
            status_code=404,
        )

    if not convo.bot_integration.saved_run_id:
        return HTMLResponse(
            "<p>Oh No! Something went wrong here.</p>"
            "<p>Please make sure this bot is connected to a gooey run or example</p>"
            + retry_button,
            status_code=400,
        )
    sr = convo.bot_integration.saved_run

    payload = json.dumps(
        dict(
            slack_channel=convo.slack_channel_name,
            slack_channel_id=convo.slack_channel_id,
            slack_user_access_token=access_token,
            slack_team_id=team_id,
            gooey_example_id=sr.example_id,
            gooey_run_id=sr.run_id,
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

slack_shortcuts_connect_url = furl(
    "https://slack.com/oauth/v2/authorize",
    query_params=dict(
        client_id=settings.SLACK_CLIENT_ID,
        scope=",".join(["incoming-webhook"]),
        user_scope=",".join(["chat:write"]),
        redirect_uri=slack_shortcuts_redirect_uri,
    ),
)


def slack_auth_header(
    authorization: str = Header(
        alias="Authorization",
        description=f"Bearer $SLACK_AUTH_TOKEN",
    ),
) -> dict:
    r = requests.post(
        "https://slack.com/api/auth.test", headers={"Authorization": authorization}
    )
    try:
        return parse_slack_response(r)
    except HTTPError:
        raise HTTPException(
            status_code=r.status_code, detail=r.content, headers=r.headers
        )
    except SlackAPIError as e:
        raise HTTPException(500, {"error": e.error})


@router.get("/__/slack/get-response-for-msg/{msg_id}/")
def slack_get_response_for_msg_id(
    msg_id: str,
    remove_refs: bool = True,
    slack_user: dict = Depends(slack_auth_header),
):
    try:
        msg = Message.objects.get(platform_msg_id=msg_id)
        response_msg = msg.get_next_by_created_at()
    except Message.DoesNotExist:
        return {"status": "not_found"}

    if msg.conversation.slack_team_id != slack_user.get(
        "team_id",
    ) and msg.conversation.slack_user_id != slack_user.get(
        "user_id",
    ):
        raise HTTPException(403, "Not authorized")

    output_text = response_msg.saved_run.state.get("output_text")
    if not output_text:
        return {"status": "no_output"}

    if remove_refs:
        output_text = "".join(snippet for snippet, _ in parse_refs(output_text, []))

    return {"status": "ok", "output_text": output_text}
