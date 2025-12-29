import asyncio
import typing
from collections import defaultdict
from typing import Dict

from fastapi import WebSocket
from furl import furl
from loguru import logger
from starlette.background import BackgroundTasks
from starlette.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse
from websockets import ConnectionClosed

from ai_models.models import AIModelSpec
from bots.models import BotIntegration
from bots.models.convo_msg import ConvoBlockedStatus
from daras_ai_v2 import settings
from daras_ai_v2.bots import msg_handler_raw
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_urlencoded_body,
    get_route_path,
)
from daras_ai_v2.ratelimits import RateLimitExceeded, ensure_bot_rate_limits
from daras_ai_v2.twilio_bot import TwilioVoice
from routers.custom_api_router import CustomAPIRouter
from routers.twilio_api import (
    twiml_response,
    resp_say_or_tts_play,
    DEFAULT_INITIAL_TEXT,
)

app = CustomAPIRouter()

T = typing.TypeVar("T")


class TwilioVoiceWs(TwilioVoice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.user_msg_id = self.call_sid

        self.input_type = "audio"
        audio_url = furl(settings.WS_PROXY_API_BASE_URL) / get_route_path(
            twilio_ws_proxy, path_params=dict(call_sid=self.call_sid)
        )
        audio_url.add(query_params={"bi_id": self.bi.api_integration_id()})
        self._audio_url = str(audio_url)
        # force gpt-4o-audio for non-audio models
        if self.saved_run and self.saved_run.state:
            llm_model = AIModelSpec.llm_objects.get(
                name=self.saved_run.state.get("selected_model")
            )
            if not llm_model.llm_is_audio_model:
                self.request_overrides = self.request_overrides or {}
                self.request_overrides["selected_model"] = "gpt_4_o_audio"

    def _send_msg(self, *args, **kwargs):
        pass


@app.post("/__/twilio/voice/ws/")
def twilio_voice_ws(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    try:
        bot = TwilioVoiceWs.from_webhook_data(data)
    except BotIntegration.DoesNotExist as e:
        logger.debug(f"could not find bot integration for {data=} {e=}")
        resp = VoiceResponse()
        resp.reject()
        return twiml_response(resp)

    if bot.convo.blocked_status == ConvoBlockedStatus.BLOCKED:
        resp = VoiceResponse()
        resp.reject()
        return twiml_response(resp)
    try:
        ensure_bot_rate_limits(bot.convo)
    except RateLimitExceeded as e:
        resp = VoiceResponse()
        resp.say(e.detail["error"])
        return twiml_response(resp)

    background_tasks.add_task(msg_handler_raw, bot)

    resp = VoiceResponse()

    text = bot.bi.twilio_initial_text.strip()
    audio_url = bot.bi.twilio_initial_audio_url.strip()
    if not text and not audio_url:
        text = DEFAULT_INITIAL_TEXT.format(bot_name=bot.bi.name)

    if audio_url:
        resp.play(audio_url)
    elif text:
        resp_say_or_tts_play(bot, resp, text, should_translate=True)

    connect = Connect()
    connect.stream(
        url=str(
            furl(settings.WS_STREAM_API_BASE_URL)
            / get_route_path(twilio_ws_stream, path_params=dict(call_sid=bot.call_sid))
        )
    )
    resp.append(connect)
    return twiml_response(resp)


@app.websocket("/__/twilio/voice/ws/stream/{call_sid}/")
async def twilio_ws_stream(websocket: WebSocket, call_sid: str):
    await _pipe_ws(websocket, call_sid, is_twilio=True)


@app.websocket("/__/twilio/voice/ws/proxy/{call_sid}/")
async def twilio_ws_proxy(websocket: WebSocket, call_sid: str):
    await _pipe_ws(websocket, call_sid, is_twilio=False)


class ValueEvent(typing.Generic[T]):
    def __init__(self) -> None:
        self.value = None
        self._event = asyncio.Event()

    def set(self, value: T | None) -> None:
        self.value = value
        if value:
            self._event.set()
        else:
            self._event.clear()

    async def wait(self) -> T | None:
        await self._event.wait()
        return self.value


class Connection:
    def __init__(self):
        self.twilio_ws = ValueEvent[WebSocket]()
        self.proxy_ws = ValueEvent[WebSocket]()


connections: Dict[str, Connection] = defaultdict(Connection)


async def _pipe_ws(source_ws: WebSocket, call_sid: str, *, is_twilio: bool):
    await source_ws.accept()

    conn = connections[call_sid]
    if is_twilio:
        source_ws_event = conn.twilio_ws
        target_ws_event = conn.proxy_ws
    else:
        source_ws_event = conn.proxy_ws
        target_ws_event = conn.twilio_ws

    source_ws_event.set(source_ws)
    target_ws = await target_ws_event.wait()
    try:
        while True:
            msg = await source_ws.receive_text()
            # print(f"> {msg=}")
            if not msg:
                return
            await target_ws.send_text(msg)
    except (WebSocketDisconnect, ConnectionClosed):
        pass
    finally:
        if is_twilio:
            try:
                await target_ws.close()
            except RuntimeError:
                pass
        connections.pop(call_sid, None)
