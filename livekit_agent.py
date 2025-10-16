from __future__ import annotations

from collections import deque

__import__("gooeysite.wsgi")

import asyncio
import uuid
from functools import wraps

import aiohttp
import requests
from asgiref.sync import sync_to_async
from decouple import config
from livekit import agents, api, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    APIConnectOptions,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    RoomInputOptions,
    function_tool,
    stt,
    tts,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr
from livekit.agents.utils import AudioBuffer
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.rtc.room import ConnectionState

from bots.models.bot_integration import BotIntegration, Platform
from bots.models.convo_msg import Conversation, db_msgs_to_entries
from daras_ai.image_input import (
    gcs_blob_for,
    gcs_bucket,
    get_mimetype_from_response,
    upload_gcs_blob_from_bytes,
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
from daras_ai_v2.language_model import ConversationEntry, LargeLanguageModels, LLMApis
from daras_ai_v2.language_model_openai_realtime import yield_from
from daras_ai_v2.text_to_speech_settings_widgets import TextToSpeechProviders
from functions.recipe_functions import WorkflowLLMTool
from number_cycling.utils import EXTENSION_NUMBER_LENGTH
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import (
    DEFAULT_TRANSLATION_MODEL,
    VideoBotsPage,
    infer_asr_model_and_language,
)
from routers.api import create_new_run

DTMF_TIMEOUT = 30
MAX_TRIES = 5

from daras_ai_v2.utils import clamp


async def entrypoint(ctx: agents.JobContext):
    from livekit.plugins import openai

    @ctx.room.on("participant_attributes_changed")
    @asyncio_create_task
    async def participant_attributes_changed(
        changed_attributes: dict, participant: rtc.Participant
    ):
        if changed_attributes.get("sip.callStatus") == "hangup":
            session.shutdown()
            ctx.shutdown()
            try:
                await ctx.api.room.delete_room(
                    api.DeleteRoomRequest(room=ctx.room.name)
                )
            except aiohttp.ServerDisconnectedError:
                pass
            await dtmf_queue.put(None)

    # logger.info(f"{ctx=}")
    await ctx.connect(rtc_config=rtc.RtcConfiguration())
    # logger.info(f"{ctx.room=}")
    if ctx.room.connection_state != ConnectionState.CONN_CONNECTED:
        return
    await ctx.wait_for_participant()
    # logger.info(f"{ctx.room.remote_participants=}")

    participant = list(ctx.room.remote_participants.values())[0]
    # logger.info(participant.attributes)
    dtmf_queue = asyncio.Queue()

    session = AgentSession(tts=openai.TTS())
    await session.start(room=ctx.room, agent=Agent(instructions=""))

    dtmf_digits = deque(maxlen=EXTENSION_NUMBER_LENGTH)

    @ctx.room.on("sip_dtmf_received")
    @asyncio_create_task
    async def sip_dtmf_received(dtmf: rtc.SipDTMF):
        # logger.info(f"{dtmf=}")
        dtmf_digits.append(dtmf.digit)
        await dtmf_queue.put(dtmf.digit)
        await session.interrupt()

    # ctx.room.on("sip_dtmf_received", sip_dtmf_received)

    for i in range(MAX_TRIES):
        if ctx.room.connection_state != ConnectionState.CONN_CONNECTED:
            return

        # wait for the user to stop typing
        if dtmf_digits or not dtmf_queue.empty():
            while True:
                try:
                    await asyncio.wait_for(dtmf_queue.get(), timeout=2)
                except asyncio.TimeoutError:
                    break

        try:
            extension_number = "".join(dtmf_digits)
            if extension_number.endswith("#"):
                input_text = "/disconnect"
            else:
                input_text = "/extension " + extension_number.split("*")[-1]
            page, request, agent, bi = await create_run(
                data=participant.attributes, input_text=input_text
            )
        except BotIntegrationLookupFailed as e:
            # logger.info(f"{e=}")
            await session.say(text=e.message, allow_interruptions=(i == 0))
            # wait for for the user to press a digit
            try:
                await asyncio.wait_for(dtmf_queue.get(), timeout=DTMF_TIMEOUT)
            except asyncio.TimeoutError:
                pass
        except UserError as e:
            # logger.info(f"{e=}")
            session.say(text=e.message, allow_interruptions=False)
            raise
        else:
            if i > 0:
                session.say(text="Connecting you to the agent")
            # logger.info(f"{dtmf_digits=} {page=} {agent=} {bi=}")
            await main(ctx, page, request, agent, bi)

            while True:
                digit = await dtmf_queue.get()
                if digit is None:  # hangup signal
                    return
                if digit == "*":  # change extension
                    break

    await session.say(
        text="You have exceeded the maximum number of attempts. Please try again later."
    )


def asyncio_create_task(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.create_task(fn(*args, **kwargs))

    return wrapper


async def main(
    ctx: agents.JobContext,
    page: VideoBotsPage,
    request: VideoBotsPage.RequestModel,
    agent: Agent,
    bi: BotIntegration,
):
    from livekit.plugins import noise_cancellation

    llm_model = LargeLanguageModels[request.selected_model]
    if llm_model.is_audio_model:
        session = await create_audio_model_session(llm_model, request)
    else:
        session = await create_stt_llm_tts_session(page, request, llm_model)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` instead for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
        ],
    )
    await background_audio.start(room=ctx.room, agent_session=session)

    if bi.twilio_initial_text:
        await session.say(text=bi.twilio_initial_text)
    else:
        await session.generate_reply(user_input="Hello")


async def create_audio_model_session(
    llm_model: LargeLanguageModels, request: VideoBotsPage.RequestModel
):
    if "gemini" in llm_model.model_id:
        from livekit.plugins import google

        llm = google.beta.realtime.RealtimeModel(
            model=llm_model.model_id, temperature=request.sampling_temperature
        )
        tts = google.TTS()
    else:
        from livekit.plugins import openai

        if llm_model.supports_temperature:
            temperature = request.sampling_temperature
            temperature = clamp(temperature, 0.6, 1.2)
        else:
            temperature = NOT_GIVEN

        llm = openai.realtime.RealtimeModel(
            model=llm_model.model_id, temperature=temperature
        )
        tts = openai.TTS()
        if request.openai_voice_name:
            llm.update_options(voice=request.openai_voice_name)
            tts.update_options(voice=request.openai_voice_name)

    return AgentSession(llm=llm, tts=tts)


async def create_stt_llm_tts_session(
    page: VideoBotsPage,
    request: VideoBotsPage.RequestModel,
    llm_model: LargeLanguageModels,
):
    from livekit.plugins import silero

    if llm_model.supports_temperature:
        temperature = request.sampling_temperature
    else:
        temperature = NOT_GIVEN

    match llm_model.llm_api:
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

        case LLMApis.openai:
            from livekit.plugins import openai

            model_id = llm_model.model_id
            if isinstance(model_id, tuple):
                model_id = model_id[-1]

            kwargs = {}
            if (
                request.reasoning_effort
                and llm_model.is_thinking_model
                and not llm_model.name.startswith("o")
            ):
                kwargs["reasoning_effort"] = request.reasoning_effort

            llm = openai.LLM(
                model=model_id,
                temperature=temperature,
                api_key=settings.OPENAI_API_KEY,
                **kwargs,
            )

        case LLMApis.mistral:
            from livekit.plugins import mistralai

            llm = mistralai.LLM(
                model=llm_model.model_id,
                temperature=temperature,
                api_key=settings.MISTRAL_API_KEY,
            )

        case LLMApis.fireworks:
            from livekit.plugins import openai

            llm = openai.LLM.with_fireworks(
                model=llm_model.model_id,
                temperature=temperature,
                api_key=settings.FIREWORKS_API_KEY,
            )

        case LLMApis.groq:
            from livekit.plugins import groq

            llm = groq.LLM(
                model=llm_model.model_id,
                temperature=temperature,
                api_key=settings.GROQ_API_KEY,
            )

        case _:
            raise UserError(f"Unsupported LLM API: {llm_model.llm_api}")

    return AgentSession(
        stt=GooeySTT(request=request),
        llm=llm,
        tts=GooeyTTS(page=page, request=request),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )


@sync_to_async
def create_run(data: dict, input_text: str):
    bot = LivekitVoice(data, input_text)

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
        run_status=None,
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

    return page, request, agent, bot.bi


def entry_to_chat_item(entry: ConversationEntry) -> agents.ChatItem:
    if isinstance(entry["content"], str):
        entry["content"] = [entry["content"]]
    return agents.ChatMessage.model_validate(entry)


class LivekitVoice(BotInterface):
    platform = Platform.TWILIO

    def __init__(self, data: dict, input_text: str):
        # "sip.ruleID": "XXXX",
        # "sip.callID": "XXXX",
        # "sip.callIDFull": "XXXX",
        # "sip.hostname": "XXXX.pstn.twilio.com",
        # "sip.twilio.callSid": "CAXXXX",
        # "sip.trunkID": "ST_XXXX",
        # "sip.callStatus": "XXXX",
        # "sip.callTag": "XXXX",
        # "sip.twilio.accountSid": "XXXX",
        # "sip.trunkPhoneNumber": "+1XXXX",
        # "sip.phoneNumber": "+1XXXX"
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
            request.tts_provider, default=TextToSpeechProviders.GOOGLE_TTS
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


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            num_idle_processes=config("MAX_THREADS", default=1, cast=int),
            job_memory_warn_mb=1024,
            job_memory_limit_mb=4096,
        )
    )
