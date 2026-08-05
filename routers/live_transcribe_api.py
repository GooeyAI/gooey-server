import fastapi
import requests

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.fastapi_tricks import fastapi_login_required
from routers.custom_api_router import CustomAPIRouter
from workspaces.widgets import get_current_workspace

app = CustomAPIRouter()

LIVE_TRANSCRIBE_MODEL = "gpt-live-transcribe"


@app.post("/__/asr/live-transcribe/token", dependencies=[fastapi_login_required])
def create_live_transcribe_token(request: fastapi.Request) -> dict:
    """Mint an ephemeral openai client secret for a browser-side realtime
    transcription session (gpt-live-transcribe over WebRTC).

    https://developers.openai.com/api/docs/guides/realtime-transcription
    """
    workspace = get_current_workspace(request.user, request.session)
    if workspace.balance < 100:
        raise fastapi.HTTPException(
            status_code=400,
            detail="You must have at least 100 credits in your workspace balance to use this feature",
        )
    r = requests.post(
        "https://api.openai.com/v1/realtime/client_secrets",
        headers={
            "Authorization": "Bearer " + settings.OPENAI_API_KEY,
            "OpenAI-Safety-Identifier": request.user.uid,
        },
        json={
            "session": {
                "type": "transcription",
                "audio": {
                    "input": {
                        # gpt-live-transcribe detects turns itself and rejects
                        # an explicit turn_detection config
                        "transcription": {
                            "model": LIVE_TRANSCRIBE_MODEL,
                            "keywords": ["Gooey.AI", "Gooey"],
                            "delay": "xhigh",
                        },
                    },
                },
            },
        },
    )
    raise_for_status(r)
    return r.json()
