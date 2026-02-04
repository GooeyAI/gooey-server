from __future__ import annotations

__import__("gooeysite.wsgi")

import asyncio
import base64
import datetime
import os
import uuid
from collections import deque
from functools import wraps
from time import time

import aiohttp
import requests
from asgiref.sync import sync_to_async
from decouple import config
from furl import furl
from livekit import agents, api, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    CloseEvent,
    ConversationItemAddedEvent,
    ErrorEvent,
    RoomInputOptions,
    function_tool,
    stt,
    tts,
)
from livekit.agents.telemetry import set_tracer_provider
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr
from livekit.agents.utils import AudioBuffer
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.rtc.room import ConnectionState

from ai_models.models import AIModelSpec, ModelProvider
from bots.models.bot_integration import BotIntegration, Platform
from bots.models.convo_msg import Conversation, db_msgs_to_entries
from bots.models.saved_run import SavedRun
from daras_ai.image_input import (
    gcs_blob_for,
    gcs_bucket,
    get_mimetype_from_response,
    upload_gcs_blob_from_bytes,
    upload_file_from_bytes,
)
from daras_ai_v2 import settings
from daras_ai_v2.asr import (
    run_asr,
    run_translate,
    should_translate_lang,
)
from daras_ai_v2.bots import BotIntegrationLookupFailed, BotInterface, build_system_vars
from daras_ai_v2.doc_search_settings_widgets import is_user_uploaded_url
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.language_model import ConversationEntry
from daras_ai_v2.language_model_openai_realtime import yield_from
from daras_ai_v2.text_to_speech_settings_widgets import TextToSpeechProviders
from daras_ai_v2.utils import clamp
from functions.recipe_functions import WorkflowLLMTool
from number_cycling.utils import EXTENSION_NUMBER_LENGTH
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import (
    DEFAULT_TRANSLATION_MODEL,
    VideoBotsPage,
    infer_asr_model_and_language,
)
from routers.api import create_new_run
from loguru import logger

DTMF_TIMEOUT = 30
MAX_TRIES = 5


server = AgentServer(
    num_idle_processes=config("MAX_THREADS", default=1, cast=int),
    job_memory_warn_mb=1024,
    job_memory_limit_mb=4096,
)


@server.rtc_session(agent_name=config("LIVEKIT_AGENT_NAME", ""))
async def entrypoint(ctx: agents.JobContext):
    setup_langfuse()

    @ctx.room.on("participant_attributes_changed")
    @asyncio_create_task
    async def participant_attributes_changed(
        changed_attributes: dict, participant: rtc.Participant
    ):
        if changed_attributes.get("sip.callStatus") == "hangup":
            dtmf_session.shutdown()
            ctx.shutdown()
            try:
                await ctx.api.room.delete_room(
                    api.DeleteRoomRequest(room=ctx.room.name)
                )
            except (aiohttp.ServerDisconnectedError, api.TwirpError):
                pass
            await dtmf_queue.put(None)

    await ctx.connect(rtc_config=rtc.RtcConfiguration())
    if ctx.room.connection_state != ConnectionState.CONN_CONNECTED:
        return
    await ctx.wait_for_participant()

    participant = list(ctx.room.remote_participants.values())[0]

    dtmf_queue, dtmf_digits, dtmf_session = await start_dtmf_session(ctx)

    prev_convo = None
    prev_session = None
    hold_player = None

    async def try_main(step):
        nonlocal prev_convo, prev_session, hold_player

        input_text = "/extension " + "".join(dtmf_digits)
        dtmf_digits.clear()

        try:
            bot = await create_livekit_voice_bot(
                data=participant.attributes, input_text=input_text
            )
        except BotIntegrationLookupFailed as e:
            # if the extension number is invalid,
            # start the hold music, say the error and wait for the user to enter the correct extension number
            prev_convo = None
            if prev_session:
                await prev_session.aclose()
                prev_session = None
            if not hold_player:
                hold_player = await start_hold_music(ctx, dtmf_session)
            dtmf_digits.clear()
            await dtmf_session.say(text=e.message, allow_interruptions=(step == 0))
            return False
        except UserError as e:
            await dtmf_session.say(text=e.message, allow_interruptions=False)
            raise

        # if the extension number hasn't changed, don't do anything
        if prev_session and prev_convo and prev_convo == bot.convo:
            return True

        if prev_session:
            await prev_session.aclose()
            prev_session = None

        page, sr, request, agent, bi = await create_run(bot)
        prev_convo = bot.convo

        if step > 0:
            new_bot_name = bi.name or "the agent"
            await dtmf_session.say(text=f"Connecting you to {new_bot_name}")
        if hold_player:
            await hold_player.aclose()
            hold_player = None

        prev_session = await main(ctx, page, sr, request, agent, bi)
        return True

    for i in range(MAX_TRIES):
        if ctx.room.connection_state != ConnectionState.CONN_CONNECTED:
            return

        success = await try_main(i)

        if success:
            # if the session is running, wait indefinitely for user input
            if await dtmf_queue.get() is None:
                return  # user hung up

        await wait_for_extension_code(dtmf_queue, dtmf_digits)

    await dtmf_session.say(
        text="You have exceeded the maximum number of attempts. Please try again later."
    )


async def start_dtmf_session(ctx: agents.JobContext):
    from livekit.plugins import google

    dtmf_queue = asyncio.Queue()

    dtmf_session = AgentSession(tts=google.TTS())
    await dtmf_session.start(room=ctx.room, agent=Agent(instructions=""), record=False)

    dtmf_digits = deque(maxlen=EXTENSION_NUMBER_LENGTH)

    @ctx.room.on("sip_dtmf_received")
    @asyncio_create_task
    async def sip_dtmf_received(dtmf: rtc.SipDTMF):
        # logger.info(f"{dtmf=}")
        if not dtmf.digit.isdigit():
            return
        dtmf_digits.append(dtmf.digit)
        await dtmf_queue.put(dtmf.digit)

    return dtmf_queue, dtmf_digits, dtmf_session


async def start_hold_music(ctx: agents.JobContext, session: AgentSession):
    wait_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(BuiltinAudioClip.HOLD_MUSIC, volume=0.1),
    )
    await wait_audio.start(room=ctx.room, agent_session=session)
    return wait_audio


async def wait_for_extension_code(dtmf_queue: asyncio.Queue, dtmf_digits: deque):
    while True:
        if len(dtmf_digits) < EXTENSION_NUMBER_LENGTH:
            # wait slowly for the full extension number
            timeout = DTMF_TIMEOUT
        else:
            # drain the queue once we have the full extension number
            timeout = 1
        try:
            if await asyncio.wait_for(dtmf_queue.get(), timeout=timeout) is None:
                return  # user hung up
        except asyncio.TimeoutError:
            break


def asyncio_create_task(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.create_task(fn(*args, **kwargs))

    return wrapper


async def main(
    ctx: agents.JobContext,
    page: VideoBotsPage,
    sr: SavedRun,
    request: VideoBotsPage.RequestModel,
    agent: Agent,
    bi: BotIntegration,
):
    llm_model = await AIModelSpec.objects.aget(name=request.selected_model)
    if llm_model.llm_is_audio_model:
        session = await create_audio_model_session(llm_model, request)
    else:
        session = await create_stt_llm_tts_session(page, request, llm_model)

    @ctx.room.on("participant_attributes_changed")
    @asyncio_create_task
    async def participant_attributes_changed(
        changed_attributes: dict, participant: rtc.Participant
    ):
        if changed_attributes.get("sip.callStatus") == "hangup":
            session.shutdown()

    @session.on("error")
    @asyncio_create_task
    async def on_error(event: ErrorEvent):
        session.say("I'm having trouble connecting right now.")
        sr.error_msg = repr(event.error)
        sr.run_time = datetime.timedelta(seconds=time() - session._started_at)
        sr.run_status = ""
        await sr.asave()

    @session.on("close")
    @session.on("conversation_item_added")
    @asyncio_create_task
    async def on_step(event: ConversationItemAddedEvent | CloseEvent):
        await save_on_step(sr, llm_model, session, event)

    ctx._primary_agent_session = None
    await session.start(room=ctx.room, agent=agent)

    if bi.twilio_initial_text:
        await session.say(text=bi.twilio_initial_text)
    else:
        await session.generate_reply(user_input="Hello")

    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
        ],
    )
    await background_audio.start(room=ctx.room, agent_session=session)

    return session


@sync_to_async
def save_on_step(
    sr: SavedRun,
    llm_model: AIModelSpec,
    session: AgentSession,
    event: ConversationItemAddedEvent | CloseEvent,
):
    sr.run_time = datetime.timedelta(seconds=time() - session._started_at)
    if isinstance(event, CloseEvent):
        sr.run_status = ""
        audio_path = session._recorder_io and session._recorder_io.output_path
        if audio_path:
            sr.state["output_audio"] = [
                upload_file_from_bytes("call_recording.ogg", audio_path.read_bytes())
            ]
    else:
        sr.run_status = f"Calling with {llm_model.label}..."

    sr.state["final_prompt"] = final_prompt = [
        item.model_dump()
        for item in session.history.items
        if item.type != "agent_handoff"
    ]
    final_prompt.sort(
        key=lambda item: (
            item.get("metrics", {}).get("stopped_speaking_at") or item.get("created_at")
        ),
    )

    sr.state["messages"] = messages = [
        {
            "role": item["role"],
            "content": (
                format_timestamp(item["created_at"] - session._started_at)
                + " ".join(item["content"])
            ),
        }
        for item in final_prompt
        if item.get("type") == "message"
    ]

    if messages and messages[-1]["role"] == "assistant":
        sr.state["output_text"] = [messages.pop()["content"]]
    else:
        sr.state["output_text"] = [""]
    if messages and messages[-1]["role"] == "user":
        sr.state["input_prompt"] = messages.pop()["content"]
    else:
        sr.state["input_prompt"] = ""

    sr.save()


def format_timestamp(elapsed: float) -> str:
    minutes, seconds = divmod(elapsed, 60)
    return f"[{minutes:02.0f}:{seconds:02.0f}] "


async def create_audio_model_session(
    llm_model: AIModelSpec, request: VideoBotsPage.RequestModel
):
    if "gemini" in llm_model.model_id:
        from livekit.plugins import google

        llm = google.beta.realtime.RealtimeModel(
            model=llm_model.model_id,
            temperature=request.sampling_temperature,
            vertexai=True,
            project=settings.GCP_PROJECT,
        )
        tts = google.TTS()
    else:
        from livekit.plugins import openai
        from openai.types.beta.realtime.session import TurnDetection

        if llm_model.llm_supports_temperature:
            temperature = request.sampling_temperature
            temperature = clamp(temperature, 0.6, 1.2)
        else:
            temperature = NOT_GIVEN

        llm = openai.realtime.RealtimeModel(
            model=llm_model.model_id,
            temperature=temperature,
            turn_detection=TurnDetection(
                type="semantic_vad",
                eagerness="auto",
                create_response=True,
                interrupt_response=True,
            ),
        )
        tts = openai.TTS()
        if request.openai_voice_name:
            llm.update_options(voice=request.openai_voice_name)
            tts.update_options(voice=request.openai_voice_name)

    return AgentSession(llm=llm, tts=tts)


async def create_stt_llm_tts_session(
    page: VideoBotsPage,
    request: VideoBotsPage.RequestModel,
    llm_model: AIModelSpec,
):
    from livekit.plugins import silero

    if llm_model.llm_supports_temperature:
        temperature = request.sampling_temperature
    else:
        temperature = NOT_GIVEN

    match llm_model.provider:
        case _ if "gemini" in llm_model.model_id:
            from livekit.plugins import google

            llm = google.LLM(
                model=llm_model.model_id.removeprefix("google/"),
                temperature=temperature,
                vertexai=True,
            )

        case _ if "claude" in llm_model.model_id:
            from livekit.plugins import anthropic

            llm = anthropic.LLM(
                model=llm_model.model_id,
                temperature=temperature,
                api_key=settings.ANTHROPIC_API_KEY,
            )

        case ModelProvider.openai:
            from livekit.plugins import openai

            model_id = llm_model.model_id
            if isinstance(model_id, tuple):
                model_id = model_id[-1]

            kwargs = {}
            if (
                request.reasoning_effort
                and llm_model.llm_is_thinking_model
                and not llm_model.name.startswith("o")
            ):
                kwargs["reasoning_effort"] = request.reasoning_effort

            if llm_model.base_url:
                base_url = llm_model.base_url
                api_key = llm_model.api_key
            elif model_id.startswith("sarvam-"):
                api_key = settings.SARVAM_API_KEY
                base_url = "https://api.sarvam.ai/v1"
            elif model_id.startswith("aisingapore/"):
                api_key = settings.SEA_LION_API_KEY
                base_url = "https://api.sea-lion.ai/v1"
            elif model_id.startswith("swiss-ai/"):
                api_key = settings.PUBLICAI_API_KEY
                base_url = "https://api.publicai.co/v1"
            elif model_id.startswith("AI71ai/"):
                import modal
                from modal_functions.agri_llm import app

                modal_fn = modal.Function.from_name(app.name, "serve")
                api_key = settings.MODAL_VLLM_API_KEY
                base_url = str(furl(modal_fn.get_web_url()) / "v1")
            else:
                api_key = settings.OPENAI_API_KEY
                base_url = NOT_GIVEN

            llm = openai.LLM(
                model=model_id,
                temperature=temperature,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )

        case ModelProvider.mistral:
            from livekit.plugins import mistralai

            llm = mistralai.LLM(
                model=llm_model.model_id,
                temperature=temperature,
                api_key=settings.MISTRAL_API_KEY,
            )

        case ModelProvider.fireworks:
            from livekit.plugins import openai

            llm = openai.LLM.with_fireworks(
                model=llm_model.model_id,
                temperature=temperature,
                api_key=settings.FIREWORKS_API_KEY,
            )

        case ModelProvider.groq:
            from livekit.plugins import groq

            llm = groq.LLM(
                model=llm_model.model_id,
                temperature=temperature,
                api_key=settings.GROQ_API_KEY,
            )

        case _:
            raise UserError(f"Unsupported LLM API: {llm_model.provider}")

    return AgentSession(
        stt=GooeySTT(request=request),
        llm=llm,
        tts=GooeyTTS(page=page, request=request),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )


@sync_to_async
def create_livekit_voice_bot(data: dict, input_text: str) -> LivekitVoice:
    return LivekitVoice(data, input_text)


@sync_to_async
def create_run(bot: LivekitVoice):
    # get latest messages for context
    saved_msgs = bot.convo.last_n_msgs()

    system_vars, system_vars_schema = build_system_vars(
        bot.convo,
        bot.user_msg_id,
        saved_msgs and saved_msgs[-1] or None,
    )
    system_vars["platform_medium"] = "VOICE"
    state = bot.saved_run.state
    variables = (state.get("variables") or {}) | system_vars
    variables_schema = (state.get("variables_schema") or {}) | system_vars_schema
    body = dict(variables=variables, variables_schema=variables_schema)
    query_params = dict(example_id=bot.bi.published_run.published_run_id)

    page, sr = create_new_run(
        page_cls=VideoBotsPage,
        query_params=query_params,
        current_user=bot.bi.created_by,
        workspace=bot.bi.workspace,
        request_body=body,
    )

    sr.transaction, sr.price = page.deduct_credits(sr.state)
    sr.save(update_fields=["transaction", "price"])

    request = VideoBotsPage.RequestModel.model_validate(sr.state)

    agent = Agent(
        instructions=request.bot_script,
        chat_ctx=agents.ChatContext(
            [entry_to_chat_item(entry) for entry in db_msgs_to_entries(saved_msgs)]
        ),
        tools=[
            create_livekit_tool(tool) for tool in page.get_current_llm_tools().values()
        ],
    )

    return page, sr, request, agent, bot.bi


def entry_to_chat_item(entry: ConversationEntry) -> agents.ChatItem:
    if isinstance(entry["content"], str):
        entry["content"] = [entry["content"]]
    return agents.ChatMessage.model_validate(entry)


class LivekitVoice(BotInterface):
    platform = Platform.TWILIO

    def __init__(self, data: dict, input_text: str):
        # data = {
        #     "sip.ruleID": "XXXX",
        #     "sip.callID": "XXXX",
        #     "sip.callIDFull": "XXXX",
        #     "sip.hostname": "XXXX.pstn.twilio.com",
        #     "sip.twilio.callSid": "CAXXXX",
        #     "sip.trunkID": "ST_XXXX",
        #     "sip.callStatus": "XXXX",
        #     "sip.callTag": "XXXX",
        #     "sip.twilio.accountSid": "XXXX",
        #     "sip.trunkPhoneNumber": "+13613043404",
        #     "sip.phoneNumber": "+12125552368",
        # }
        self.bot_id = data["sip.trunkPhoneNumber"]
        self.user_id = data["sip.phoneNumber"]

        self._input_text = input_text

        call_sid = data["sip.twilio.callSid"]
        account_sid = data["sip.twilio.accountSid"]
        if account_sid == settings.TWILIO_ACCOUNT_SID:
            account_sid = ""
        # print(f"{user_number=} {bot_number=} {call_sid=} {account_sid=}")

        bi = self.lookup_bot_integration(
            bot_lookup=dict(twilio_phone_number=self.bot_id),
            user_lookup=dict(twilio_phone_number=self.user_id),
        )
        if bi.twilio_fresh_conversation_per_call:
            self.convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                twilio_phone_number=self.user_id,
                twilio_call_sid=call_sid,
            )[0]
        else:
            self.convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                twilio_phone_number=self.user_id,
                twilio_call_sid="",
            )[0]

        super().__init__()

    def get_input_text(self) -> str | None:
        return self._input_text


def create_livekit_tool(tool: WorkflowLLMTool):
    async def handler(raw_arguments: dict[str, object], context: agents.RunContext):
        from asgiref.sync import sync_to_async

        try:
            # print("call_livekit", tool.name, raw_arguments, context)
            ret = await sync_to_async(tool.call)(**raw_arguments)
            # print("call_livekit", tool.name, raw_arguments, context, ret)
            return ret
        except TypeError as e:
            return dict(error=repr(e))

    return function_tool(handler, raw_schema=tool.spec_openai_audio)


@sync_to_async
def asr_step(request: VideoBotsPage.RequestModel, buffer: AudioBuffer) -> str:
    if not request.asr_model:
        request.asr_model, request.asr_language = infer_asr_model_and_language(
            request.user_language or ""
        )
    blob = gcs_blob_for(filename="audio.wav")
    try:
        upload_gcs_blob_from_bytes(blob, buffer.to_wav_bytes(), "audio/wav")
        user_input = run_asr(
            audio_url=blob.public_url,
            selected_model=request.asr_model,
            language=request.asr_language,
            speech_translation_target=(
                "en" if request.asr_task == "translate" else None
            ),
            input_prompt=request.asr_prompt,
        )
    finally:
        blob.delete()

    request.translation_model = request.translation_model or DEFAULT_TRANSLATION_MODEL
    if (
        should_translate_lang(request.user_language)
        and not request.asr_task == "translate"
    ):
        user_input = run_translate(
            texts=[user_input],
            source_language=request.user_language,
            glossary_url=request.input_glossary_document,
            target_language="en",
            model=request.translation_model,
        )[0]

    return user_input


class GooeySTT(stt.STT):
    def __init__(self, request: VideoBotsPage.RequestModel):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )
        self.request = request

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(
                    text=await asr_step(self.request, buffer), language="en"
                ),
            ],
        )


class GooeyTTS(tts.TTS):
    def __init__(self, page: VideoBotsPage, request: VideoBotsPage.RequestModel):
        tts_provider = TextToSpeechProviders.get(
            request.tts_provider, default=TextToSpeechProviders.OPEN_AI
        )
        self.tts_sample_rate = tts_provider.sample_rate
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=self.tts_sample_rate,
            num_channels=1,
        )
        self.page = page
        self.request = request

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> ChunkedStream:
        return ChunkedStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
            page=self.page,
            request=self.request,
            sample_rate=self.tts_sample_rate,
        )


class ChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts: GooeyTTS,
        input_text: str,
        conn_options: APIConnectOptions,
        page: VideoBotsPage,
        request: VideoBotsPage.RequestModel,
        sample_rate: int,
    ):
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self.page = page
        self.request = request
        self.tts_sample_rate = sample_rate

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        audio_wav_bytes, mime_type = await tts_step(
            self.page, self.request, self.input_text
        )
        output_emitter.initialize(
            request_id=str(uuid.uuid4()),
            sample_rate=self.tts_sample_rate,
            num_channels=1,
            mime_type=mime_type,
        )
        output_emitter.push(audio_wav_bytes)
        output_emitter.flush()


@sync_to_async
def tts_step(
    page: VideoBotsPage, request: VideoBotsPage.RequestModel, input_text: str
) -> bytes:
    if should_translate_lang(request.user_language):
        input_text = run_translate(
            texts=[input_text],
            source_language="en",
            target_language=request.user_language,
            glossary_url=request.output_glossary_document,
            model=request.translation_model,
        )[0]

    tts_state = TextToSpeechPage.RequestModel.model_validate(
        request.model_dump() | dict(text_prompt=input_text)
    ).model_dump()
    yield_from(TextToSpeechPage(request=page.request).run(tts_state))
    audio_url = tts_state["audio_url"]
    try:
        r = requests.get(audio_url)
        raise_for_status(r)
        audio_wav_bytes = r.content
        mime_type = get_mimetype_from_response(r)
    finally:
        if is_user_uploaded_url(audio_url):
            blob = gcs_bucket().blob(
                audio_url.split(settings.GS_BUCKET_NAME)[-1].strip("/")
            )
            blob.delete()
    return audio_wav_bytes, mime_type


# https://docs.livekit.io/deploy/observability/data/#opentelemetry-integration
def setup_langfuse():
    if not (
        settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
        and settings.LANGFUSE_BASE_URL
    ):
        logger.warning(
            "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL must be set for langfuse telemetry"
        )
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    langfuse_auth = base64.b64encode(
        f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}".encode()
    ).decode()
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
        f"{settings.LANGFUSE_BASE_URL.rstrip('/')}/api/public/otel"
    )
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {langfuse_auth}"

    trace_provider = TracerProvider()
    trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    set_tracer_provider(trace_provider)


if __name__ == "__main__":
    agents.cli.run_app(server)
