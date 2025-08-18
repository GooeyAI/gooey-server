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

from bots.models import BotIntegration, Conversation
from bots.models.convo_msg import ConvoBlockedStatus
from daras_ai_v2 import settings
from daras_ai_v2.bots import msg_handler_raw
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_urlencoded_body,
    get_route_path,
    get_api_route_url,
)
from daras_ai_v2.ratelimits import RateLimitExceeded, ensure_bot_rate_limits
from daras_ai_v2.twilio_bot import TwilioVoice
from routers.custom_api_router import CustomAPIRouter
from routers.twilio_api import (
    twiml_response,
    resp_say_or_tts_play,
    DEFAULT_INITIAL_TEXT,
)
from daras_ai_v2.language_model import LargeLanguageModels
from number_cycling.models import ProvisionedNumber, BotExtensionUser, BotExtension

app = CustomAPIRouter()

T = typing.TypeVar("T")


class NeedsExtensionGathering(Exception):
    """Exception raised when a user needs to provide an extension number."""

    def __init__(self, call_sid: str, user_number: str):
        self.call_sid = call_sid
        self.user_number = user_number
        super().__init__(
            f"Extension gathering needed for {user_number} on call {call_sid}"
        )


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
            llm_model = LargeLanguageModels[self.saved_run.state.get("selected_model")]
            if not llm_model.is_audio_model:
                self.request_overrides = self.request_overrides or {}
                self.request_overrides["selected_model"] = (
                    LargeLanguageModels.gpt_4_o_audio.name
                )

    @classmethod
    def from_webhook_data(cls, data: dict):
        logger.debug(data)
        account_sid = data["AccountSid"][0]
        if account_sid == settings.TWILIO_ACCOUNT_SID:
            account_sid = ""
        call_sid = data["CallSid"][0]
        user_number, bot_number = data["From"][0], data["To"][0]
        current_ext = None

        try:
            ProvisionedNumber.objects.get(phone_number=bot_number)
            try:
                existing_mapping = BotExtensionUser.objects.get(
                    twilio_phone_number=user_number
                )
                current_ext = existing_mapping.extension
                bi = current_ext.bot_integration
            except BotExtensionUser.DoesNotExist:
                raise NeedsExtensionGathering(call_sid, user_number)

        except ProvisionedNumber.DoesNotExist:
            try:
                # cases where user is calling the bot
                bi = BotIntegration.objects.get(
                    twilio_account_sid=account_sid, twilio_phone_number=bot_number
                )
            except BotIntegration.DoesNotExist:
                #  cases where bot is calling the user
                user_number, bot_number = bot_number, user_number
                bi = BotIntegration.objects.get(
                    twilio_account_sid=account_sid, twilio_phone_number=bot_number
                )

        return create_twilio_voice_ws_bot(
            bi=bi,
            user_number=user_number,
            call_sid=call_sid,
            extension=current_ext,
            text=data.get("SpeechResult", [None])[0],
            audio_url=data.get("RecordingUrl", [None])[0],
        )

    def _send_msg(self, *args, **kwargs):
        pass


@app.post("/__/twilio/voice/ws/")
def twilio_voice_ws(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    try:
        bot = TwilioVoiceWs.from_webhook_data(data)
    except NeedsExtensionGathering as e:
        resp = VoiceResponse()
        resp.say("Hi from Gooey.AI, Please enter an extension")
        resp.gather(
            action=get_api_route_url(twilio_extension_input),
            method="POST",
            numDigits=5,
            timeout=10,
        )
        resp.say("No extension entered. Goodbye.")
        resp.reject()
        return twiml_response(resp)
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
    return connect_to_stream(bot)


@app.post("/__/twilio/voice/ws/extension/")
def twilio_extension_input(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    call_sid = data["CallSid"][0]
    user_number = data["From"][0]
    digits = data.get("Digits", [None])[0]

    logger.debug(f"Extension input: {digits=} {call_sid=} {user_number=}")
    if not digits:
        resp = VoiceResponse()
        resp.say("No extension entered. Goodbye.")
        resp.reject()
        return twiml_response(resp)

    try:
        extension = BotExtension.objects.get(extension_number=int(digits))
    except (BotExtension.DoesNotExist, ValueError):
        resp = VoiceResponse()
        resp.say("Invalid extension entered. Goodbye.")
        resp.reject()
        return twiml_response(resp)

    # Create or update the user extension mapping
    mapping, created = BotExtensionUser.objects.get_or_create(
        twilio_phone_number=user_number, defaults={"extension": extension}
    )

    if not created:
        mapping.extension = extension
        mapping.save()

    logger.debug(
        f"Creating twilio voice ws bot instance for {user_number=} {call_sid=} {extension=}"
    )
    bi = extension.bot_integration
    bot = create_twilio_voice_ws_bot(
        bi=bi,
        user_number=user_number,
        call_sid=call_sid,
        extension=extension,
        text=data.get("SpeechResult", [None])[0],
        audio_url=data.get("RecordingUrl", [None])[0],
    )

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
    return connect_to_stream(bot)


def connect_to_stream(bot: TwilioVoiceWs):
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


def create_twilio_voice_ws_bot(
    bi: BotIntegration,
    user_number: str,
    call_sid: str,
    extension: BotExtension | None = None,
    text: str | None = None,
    audio_url: str | None = None,
):
    if bi.twilio_use_missed_call:
        convo = Conversation(
            bot_integration=bi,
            twilio_phone_number=user_number,
            twilio_call_sid=call_sid,
            extension=extension,
        )
    elif bi.twilio_fresh_conversation_per_call:
        convo = Conversation.objects.get_or_create(
            bot_integration=bi,
            twilio_phone_number=user_number,
            twilio_call_sid=call_sid,
            extension=extension,
        )[0]
    else:
        convo = Conversation.objects.get_or_create(
            bot_integration=bi,
            twilio_phone_number=user_number,
            twilio_call_sid="",
            extension=extension,
        )[0]

    return TwilioVoiceWs(
        convo,
        text=text,
        audio_url=audio_url,
        call_sid=call_sid,
    )


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
