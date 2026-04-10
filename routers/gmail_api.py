"""
Gmail API router:
  - OAuth2 callback to connect a user's Gmail account
  - Pub/Sub webhook endpoint to receive push notifications from Gmail watch()
"""

import base64
import json
import logging

from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from furl import furl
from starlette.requests import Request

from daras_ai_v2 import settings
from daras_ai_v2.gmail_bot import (
    build_auth_url,
    exchange_code_for_tokens,
    get_history_since,
    get_message,
    get_user_email,
    gmail_watch,
    parse_message,
    refresh_access_token,
)
from routers.custom_api_router import CustomAPIRouter

logger = logging.getLogger(__name__)

app = CustomAPIRouter()


# ---------------------------------------------------------------------------
# OAuth2 connect flow
# ---------------------------------------------------------------------------


@app.get("/__/gmail/connect/")
def gmail_connect_redirect(request: Request):
    """
    OAuth2 callback from Google after user authorizes Gmail access.
    Exchanges the code for tokens, stores them, and starts watch().
    """
    from bots.models import SavedRun
    from daras_ai_v2.base import SUBMIT_AFTER_LOGIN_Q

    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Gmail auth failed: {error}")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    state = json.loads(request.query_params.get("state") or "{}")
    sr_id = state.get("sr_id")

    try:
        sr = SavedRun.objects.get(id=sr_id)
    except SavedRun.DoesNotExist:
        raise HTTPException(status_code=404, detail="SavedRun not found")

    # Exchange code for tokens
    token_data = exchange_code_for_tokens(code, redirect_uri=_redirect_url())

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    # Get user's email for display
    email = get_user_email(access_token)

    # Store on workspace
    ws = sr.workspace
    ws.gmail_access_token = access_token
    ws.gmail_refresh_token = refresh_token
    ws.gmail_user_email = email
    ws.save(update_fields=["gmail_access_token", "gmail_refresh_token", "gmail_user_email"])

    # Start watching for new mail
    watch_data = gmail_watch(access_token)
    ws.gmail_history_id = watch_data.get("historyId", "")
    ws.save(update_fields=["gmail_history_id"])

    logger.info("Gmail connected for workspace=%s email=%s", ws.id, email)

    redirect_url = sr.get_app_url({SUBMIT_AFTER_LOGIN_Q: "1"})
    return RedirectResponse(redirect_url)


def generate_gmail_auth_url(sr_id: int) -> str:
    """Build the OAuth URL to start Gmail authorization."""
    return build_auth_url(
        redirect_uri=_redirect_url(),
        state=json.dumps({"sr_id": sr_id}),
    )


def _redirect_url() -> str:
    return (
        furl(settings.APP_BASE_URL) / app.url_path_for(gmail_connect_redirect.__name__)
    ).tostr()


# ---------------------------------------------------------------------------
# Pub/Sub webhook — receives push notifications from Gmail
# ---------------------------------------------------------------------------


@app.post("/__/gmail/webhook/")
async def gmail_pubsub_webhook(request: Request):
    """
    Receives push notifications from Google Pub/Sub when a watched
    Gmail inbox gets new mail.

    The Pub/Sub message body is:
        {"message": {"data": base64("{"emailAddress":"...","historyId":"..."}"), ...}}
    """
    body = await request.json()
    message = body.get("message", {})
    data_b64 = message.get("data", "")

    if not data_b64:
        logger.warning("Gmail webhook received empty data")
        return {"status": "ignored"}

    payload = json.loads(base64.urlsafe_b64decode(data_b64))
    email_address = payload.get("emailAddress", "")
    new_history_id = payload.get("historyId", "")

    logger.info("Gmail push notification: email=%s historyId=%s", email_address, new_history_id)

    # Look up the workspace by email
    from workspaces.models import Workspace

    try:
        ws = Workspace.objects.get(gmail_user_email=email_address)
    except Workspace.DoesNotExist:
        logger.warning("No workspace found for Gmail email=%s", email_address)
        return {"status": "no_workspace"}
    except Workspace.MultipleObjectsReturned:
        ws = Workspace.objects.filter(gmail_user_email=email_address).first()

    # Refresh token if needed, then fetch new messages
    access_token = ws.gmail_access_token
    old_history_id = ws.gmail_history_id or new_history_id

    try:
        new_messages = get_history_since(access_token, old_history_id)
    except Exception:
        # Token might be expired — refresh and retry
        try:
            token_data = refresh_access_token(ws.gmail_refresh_token)
            access_token = token_data["access_token"]
            ws.gmail_access_token = access_token
            ws.save(update_fields=["gmail_access_token"])
            new_messages = get_history_since(access_token, old_history_id)
        except Exception:
            logger.exception("Failed to fetch Gmail history for %s", email_address)
            return {"status": "error"}

    # Update stored historyId
    ws.gmail_history_id = new_history_id
    ws.save(update_fields=["gmail_history_id"])

    # Process each new message
    parsed_messages = []
    for msg_stub in new_messages:
        try:
            full_msg = get_message(access_token, msg_stub["id"])
            parsed = parse_message(full_msg)
            parsed_messages.append(parsed)
            logger.info(
                "New Gmail: from=%s subject=%s",
                parsed["from"],
                parsed["subject"],
            )
        except Exception:
            logger.exception("Failed to fetch message %s", msg_stub.get("id"))

    # TODO: do something with parsed_messages — e.g. trigger a bot workflow,
    # store in DB, forward to a Celery task, etc.
    logger.info("Processed %d new Gmail messages for %s", len(parsed_messages), email_address)

    return {"status": "ok", "messages_processed": len(parsed_messages)}
