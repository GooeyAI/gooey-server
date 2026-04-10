"""
Gmail API integration using watch() for push notifications via Google Pub/Sub.

Flow:
1. User authorizes via OAuth2 -> we store access_token + refresh_token
2. We call watch() to register push notifications on their inbox
3. Google sends a Pub/Sub notification to our webhook when new mail arrives
4. We fetch the new message(s) using the history API

Setup required:
- Create a GCP Pub/Sub topic (e.g. "gmail-push")
- Grant gmail-api-push@system.gserviceaccount.com "Pub/Sub Publisher" on that topic
- Create a push subscription pointing to your webhook URL
- Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET env vars
"""

import base64
import logging
from email.utils import parseaddr

import requests
from google.oauth2.credentials import Credentials

from daras_ai_v2 import settings

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def build_auth_url(*, redirect_uri: str, state: str) -> str:
    """Build the Google OAuth2 authorization URL for Gmail access."""
    from furl import furl

    return furl(
        GOOGLE_AUTH_URL,
        query_params={
            "client_id": settings.GMAIL_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(settings.GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        },
    ).tostr()


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    r = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        },
    )
    r.raise_for_status()
    return r.json()  # {access_token, refresh_token, expires_in, ...}


def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh token to get a new access token."""
    r = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    r.raise_for_status()
    return r.json()  # {access_token, expires_in, ...}


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def get_user_email(access_token: str) -> str:
    """Get the authenticated user's email address."""
    r = requests.get(
        f"{GMAIL_API_BASE}/users/me/profile",
        headers=_auth_headers(access_token),
    )
    r.raise_for_status()
    return r.json()["emailAddress"]


# ---------------------------------------------------------------------------
# watch() — register for push notifications
# ---------------------------------------------------------------------------


def gmail_watch(access_token: str) -> dict:
    """
    Call Gmail watch() to receive Pub/Sub push notifications for new mail.

    Returns:
        {"historyId": "12345", "expiration": "1234567890000"}

    The watch expires after ~7 days — renew it with a periodic task.
    """
    r = requests.post(
        f"{GMAIL_API_BASE}/users/me/watch",
        headers=_auth_headers(access_token),
        json={
            "topicName": settings.GMAIL_PUBSUB_TOPIC,
            "labelIds": ["INBOX"],
        },
    )
    r.raise_for_status()
    data = r.json()
    logger.info("gmail watch registered: historyId=%s expiration=%s", data.get("historyId"), data.get("expiration"))
    return data


def gmail_stop(access_token: str):
    """Stop receiving push notifications for this user."""
    r = requests.post(
        f"{GMAIL_API_BASE}/users/me/stop",
        headers=_auth_headers(access_token),
    )
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Fetch new messages via history API
# ---------------------------------------------------------------------------


def get_history_since(access_token: str, history_id: str) -> list[dict]:
    """
    Fetch message IDs added since the given historyId.

    Returns a list of {"id": "...", "threadId": "..."} dicts for new messages.
    """
    r = requests.get(
        f"{GMAIL_API_BASE}/users/me/history",
        headers=_auth_headers(access_token),
        params={
            "startHistoryId": history_id,
            "historyTypes": "messageAdded",
            "labelId": "INBOX",
        },
    )
    if r.status_code == 404:
        # historyId is too old — caller should do a full sync
        logger.warning("historyId %s is too old, returning empty", history_id)
        return []
    r.raise_for_status()

    data = r.json()
    messages = []
    for record in data.get("history", []):
        for msg in record.get("messagesAdded", []):
            messages.append(msg["message"])
    return messages


def get_message(access_token: str, message_id: str, fmt: str = "full") -> dict:
    """
    Fetch a single message by ID.

    Args:
        fmt: "full", "metadata", "minimal", or "raw"

    Returns the Gmail message resource.
    """
    r = requests.get(
        f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
        headers=_auth_headers(access_token),
        params={"format": fmt},
    )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_message(msg: dict) -> dict:
    """
    Extract useful fields from a Gmail message resource (format=full).

    Returns:
        {
            "id": str,
            "thread_id": str,
            "from": str,
            "to": str,
            "subject": str,
            "date": str,
            "snippet": str,
            "body_text": str,
            "label_ids": list[str],
        }
    """
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

    body_text = _extract_body_text(msg.get("payload", {}))

    return {
        "id": msg["id"],
        "thread_id": msg["threadId"],
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "body_text": body_text,
        "label_ids": msg.get("labelIds", []),
    }


def _extract_body_text(payload: dict) -> str:
    """Recursively extract text/plain body from a message payload."""
    mime_type = payload.get("mimeType", "")

    # Simple single-part message
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Multipart — recurse into parts
    for part in payload.get("parts", []):
        text = _extract_body_text(part)
        if text:
            return text

    return ""
