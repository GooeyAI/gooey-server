from __future__ import annotations

from decouple import config

__import__("gooeysite.wsgi")

from routers.api import create_new_run

from daras_ai_v2.text_to_speech_settings_widgets import TextToSpeechProviders

from daras_ai_v2.bots import BotInterface, build_system_vars


from bots.models.convo_msg import Conversation, db_msgs_to_entries

import uuid

import requests
from asgiref.sync import sync_to_async
from livekit import agents
from livekit.rtc.room import ConnectionState
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

from bots.models.bot_integration import BotIntegration, Platform
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
from daras_ai_v2.doc_search_settings_widgets import is_user_uploaded_url
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.language_model import ConversationEntry, LargeLanguageModels, LLMApis
from daras_ai_v2.language_model_openai_realtime import yield_from
from functions.recipe_functions import WorkflowLLMTool
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import (
    DEFAULT_TRANSLATION_MODEL,
    VideoBotsPage,
    infer_asr_model_and_language,
)


async def entrypoint(ctx: agents.JobContext):
    from livekit.plugins import noise_cancellation

    await ctx.connect()
    # print(f"{ctx.room=}")
    if ctx.room.connection_state != ConnectionState.CONN_CONNECTED:
        return
    # print(f"{ctx.room.remote_participants=}")
    await ctx.wait_for_participant()
    # print(f"{ctx.room.remote_participants=}")
    participant = list(ctx.room.remote_participants.values())[0]
    page, request, agent, bi = await create_run(participant.attributes)

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

        llm = openai.realtime.RealtimeModel(
            model=llm_model.model_id, temperature=request.sampling_temperature
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

    match llm_model.llm_api:
        case LLMApis.openai:
            from livekit.plugins import openai

            model_id = llm_model.model_id
            if isinstance(model_id, tuple):
                model_id = model_id[-1]
            llm = openai.LLM(model=model_id, temperature=request.sampling_temperature)

        case _ if "gemini" in llm_model.model_id:
            from livekit.plugins import google

            llm = google.LLM(
                model=llm_model.model_id, temperature=request.sampling_temperature
            )

        case _ if "claude" in llm_model.model_id:
            from livekit.plugins import anthropic

            llm = anthropic.Claude(
                model=llm_model.model_id, temperature=request.sampling_temperature
            )

        case LLMApis.mistral:
            from livekit.plugins import mistralai

            llm = mistralai.LLM(
                model=llm_model.model_id, temperature=request.sampling_temperature
            )

        case LLMApis.fireworks:
            from livekit.plugins import openai

            llm = openai.LLM.with_fireworks(
                model=llm_model.model_id, temperature=request.sampling_temperature
            )

        case LLMApis.groq:
            from livekit.plugins import groq

            llm = groq.LLM(
                model=llm_model.model_id, temperature=request.sampling_temperature
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
def create_run(data):
    bot = LivekitVoice.from_ctx(data)

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

    @classmethod
    def from_ctx(cls, data: dict):
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

        user_number = data["sip.phoneNumber"]
        bot_number = data["sip.trunkPhoneNumber"]
        call_sid = data["sip.twilio.callSid"]
        account_sid = data["sip.twilio.accountSid"]
        if account_sid == settings.TWILIO_ACCOUNT_SID:
            account_sid = ""
        # print(f"{user_number=} {bot_number=} {call_sid=} {account_sid=}")

        try:
            # cases where user is calling the bot
            bi = BotIntegration.objects.get(
                twilio_account_sid=account_sid, twilio_phone_number=bot_number
            )
            will_be_missed = bi.twilio_use_missed_call
        except BotIntegration.DoesNotExist:
            #  cases where bot is calling the user
            user_number, bot_number = bot_number, user_number
            bi = BotIntegration.objects.get(
                twilio_account_sid=account_sid, twilio_phone_number=bot_number
            )
            will_be_missed = False

        if will_be_missed:
            # for calls that we will reject and callback, the convo is not used so we don't want to create one
            convo = Conversation(
                bot_integration=bi,
                twilio_phone_number=user_number,
                twilio_call_sid=call_sid,
            )
        elif bi.twilio_fresh_conversation_per_call:
            convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                twilio_phone_number=user_number,
                twilio_call_sid=call_sid,
            )[0]
        else:
            convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                twilio_phone_number=user_number,
                twilio_call_sid="",
            )[0]

        return cls(convo, call_sid=call_sid)

    def __init__(self, convo: Conversation, *, call_sid: str):
        self.convo = convo

        self.bot_id = convo.bot_integration.twilio_phone_number.as_e164
        self.user_id = convo.twilio_phone_number.as_e164

        self.call_sid = call_sid

        super().__init__()


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
        self.tts_provider = TextToSpeechProviders.get(
            request.tts_provider, default=TextToSpeechProviders.GOOGLE_TTS
        )
        self.tts_sample_rate = self.tts_provider.sample_rate
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
