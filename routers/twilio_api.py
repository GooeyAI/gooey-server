import random
import traceback
from time import sleep

from fastapi import APIRouter, Response
from loguru import logger
from sentry_sdk import capture_exception
from starlette.background import BackgroundTasks
from twilio.twiml import TwiML
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather

from app_users.models import AppUser
from bots.models import Conversation, BotIntegration
from daras_ai_v2.bots import msg_handler
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_urlencoded_body,
    get_api_route_url,
)
from daras_ai_v2.twilio_bot import TwilioVoice
from gooeysite.bg_db_conn import get_celery_result_db_safe
from recipes.TextToSpeech import TextToSpeechPage

DEFAULT_INITIAL_TEXT = "Welcome to {bot_name}! Please ask your question and press 0 if the end of your question isn't detected."
DEFAULT_WAITING_AUDIO_URLS = [
    "http://com.twilio.sounds.music.s3.amazonaws.com/ClockworkWaltz.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/BusyStrings.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/oldDog_-_endless_goodbye_%28instr.%29.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/Mellotroniac_-_Flight_Of_Young_Hearts_Flute.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/MARKOVICHAMP-Borghestral.mp3",
]
DEFAULT_VOICE_NAME = "Google.en-US-Wavenet-F"
DEFAULT_ASR_LANGUAGE = "en-US"
TWILIO_SUPPORTED_VOICES = {"Google.af-ZA-Standard-A", "Polly.Zeina", "Google.ar-XA-Standard-A", "Google.ar-XA-Standard-B", "Google.ar-XA-Standard-C", "Google.ar-XA-Standard-D", "Google.ar-XA-Wavenet-A", "Google.ar-XA-Wavenet-B", "Google.ar-XA-Wavenet-C", "Google.ar-XA-Wavenet-D", "Polly.Hala-Neural", "Polly.Zayd-Neural", "Google.eu-ES-Standard-A", "Google.bn-IN-Standard-C", "Google.bn-IN-Standard-D", "Google.bn-IN-Wavenet-C", "Google.bn-IN-Wavenet-D", "Google.bg-BG-Standard-A", "Polly.Arlet-Neural", "Google.ca-ES-Standard-A", "Polly.Hiujin-Neural", "Google.yue-HK-Standard-A", "Google.yue-HK-Standard-B", "Google.yue-HK-Standard-C", "Google.yue-HK-Standard-D", "Polly.Zhiyu", "Polly.Zhiyu-Neural", "Google.cmn-CN-Standard-A", "Google.cmn-CN-Standard-B", "Google.cmn-CN-Standard-C", "Google.cmn-CN-Standard-D", "Google.cmn-CN-Wavenet-A", "Google.cmn-CN-Wavenet-B", "Google.cmn-CN-Wavenet-C", "Google.cmn-CN-Wavenet-D", "Google.cmn-TW-Standard-A", "Google.cmn-TW-Standard-B", "Google.cmn-TW-Standard-C", "Google.cmn-TW-Wavenet-A", "Google.cmn-TW-Wavenet-B", "Google.cmn-TW-Wavenet-C", "Google.cs-CZ-Standard-A", "Google.cs-CZ-Wavenet-A", "Polly.Mads", "Polly.Naja", "Polly.Sofie-Neural", "Google.da-DK-Standard-A", "Google.da-DK-Standard-C", "Google.da-DK-Standard-D", "Google.da-DK-Standard-E", "Google.da-DK-Wavenet-A", "Google.da-DK-Wavenet-C", "Google.da-DK-Wavenet-D", "Google.da-DK-Wavenet-E", "Polly.Lisa-Neural", "Google.nl-BE-Standard-A", "Google.nl-BE-Standard-B", "Google.nl-BE-Wavenet-A", "Google.nl-BE-Wavenet-B", "Polly.Lotte", "Polly.Ruben", "Polly.Laura-Neural", "Google.nl-NL-Standard-A", "Google.nl-NL-Standard-B", "Google.nl-NL-Standard-C", "Google.nl-NL-Standard-D", "Google.nl-NL-Standard-E", "Google.nl-NL-Wavenet-A", "Google.nl-NL-Wavenet-B", "Google.nl-NL-Wavenet-C", "Google.nl-NL-Wavenet-D", "Google.nl-NL-Wavenet-E", "Polly.Nicole", "Polly.Russell", "Polly.Olivia-Neural", "Google.en-AU-Standard-A", "Google.en-AU-Standard-B", "Google.en-AU-Standard-C", "Google.en-AU-Standard-D", "Google.en-AU-Wavenet-A", "Google.en-AU-Wavenet-B", "Google.en-AU-Wavenet-C", "Google.en-AU-Wavenet-D", "Google.en-AU-Neural2-A", "Google.en-AU-Neural2-B", "Google.en-AU-Neural2-C", "Google.en-AU-Neural2-D", "Polly.Raveena", "Google.en-IN-Standard-A", "Google.en-IN-Standard-B", "Google.en-IN-Standard-C", "Google.en-IN-Standard-D", "Google.en-IN-Wavenet-A", "Google.en-IN-Wavenet-B", "Google.en-IN-Wavenet-C", "Google.en-IN-Wavenet-D", "Google.en-IN-Neural2-A", "Google.en-IN-Neural2-B", "Google.en-IN-Neural2-C", "Google.en-IN-Neural2-D", "Polly.Niamh-Neural", "Polly.Aria-Neural", "Polly.Ayanda-Neural", "Polly.Amy", "Polly.Brian", "Polly.Emma", "Polly.Amy-Neural", "Polly.Emma-Neural", "Polly.Brian-Neural", "Polly.Arthur-Neural", "Google.en-GB-Standard-A", "Google.en-GB-Standard-B", "Google.en-GB-Standard-C", "Google.en-GB-Standard-D", "Google.en-GB-Standard-F", "Google.en-GB-Wavenet-A", "Google.en-GB-Wavenet-B", "Google.en-GB-Wavenet-C", "Google.en-GB-Wavenet-D", "Google.en-GB-Wavenet-F", "Google.en-GB-Neural2-A", "Google.en-GB-Neural2-B", "Google.en-GB-Neural2-C", "Google.en-GB-Neural2-D", "Google.en-GB-Neural2-F", "Polly.Ivy", "Polly.Joanna", "Polly.Joey", "Polly.Justin", "Polly.Kendra", "Polly.Kimberly", "Polly.Matthew", "Polly.Salli", "child)	Polly.Ivy-Neural", "Polly.Joanna-Neural*", "Polly.Kendra-Neural", "child)	Polly.Kevin-Neural", "Polly.Kimberly-Neural", "Polly.Salli-Neural", "Polly.Joey-Neural", "child)	Polly.Justin-Neural", "Polly.Matthew-Neural*", "Polly.Ruth-Neural", "Polly.Stephen-Neural", "Polly.Gregory-Neural", "Polly.Danielle-Neural", "Google.en-US-Standard-A", "Google.en-US-Standard-B", "Google.en-US-Standard-C", "Google.en-US-Standard-D", "Google.en-US-Standard-E", "Google.en-US-Standard-F", "Google.en-US-Standard-G", "Google.en-US-Standard-H", "Google.en-US-Standard-I", "Google.en-US-Standard-J", "Google.en-US-Wavenet-A", "Google.en-US-Wavenet-B", "Google.en-US-Wavenet-C", "Google.en-US-Wavenet-D", "Google.en-US-Wavenet-E", "Google.en-US-Wavenet-F", "Google.en-US-Wavenet-G", "Google.en-US-Wavenet-H", "Google.en-US-Wavenet-I", "Google.en-US-Wavenet-J", "Google.en-US-Neural2-A", "Google.en-US-Neural2-C", "Google.en-US-Neural2-D", "Google.en-US-Neural2-E", "Google.en-US-Neural2-F", "Google.en-US-Neural2-G", "Google.en-US-Neural2-H", "Google.en-US-Neural2-I", "Google.en-US-Neural2-J", "Polly.Geraint", "Google.fil-PH-Standard-A", "Google.fil-PH-Standard-B", "Google.fil-PH-Standard-C", "Google.fil-PH-Standard-D", "Google.fil-PH-Wavenet-A", "Google.fil-PH-Wavenet-B", "Google.fil-PH-Wavenet-C", "Google.fil-PH-Wavenet-D", "Polly.Suvi-Neural", "Google.fi-FI-Standard-A", "Google.fi-FI-Wavenet-A", "Polly.Isabelle-Neural", "Polly.Chantal", "Polly.Gabrielle-Neural", "Polly.Liam-Neural", "Google.fr-CA-Standard-A", "Google.fr-CA-Standard-B", "Google.fr-CA-Standard-C", "Google.fr-CA-Standard-D", "Google.fr-CA-Wavenet-A", "Google.fr-CA-Wavenet-B", "Google.fr-CA-Wavenet-C", "Google.fr-CA-Wavenet-D", "Google.fr-CA-Neural2-A", "Google.fr-CA-Neural2-B", "Google.fr-CA-Neural2-C", "Google.fr-CA-Neural2-D", "Polly.Céline/Polly.Celine", "Polly.Léa/Polly.Lea", "Polly.Mathieu", "Polly.Lea-Neural", "Polly.Remi-Neural", "Google.fr-FR-Standard-A", "Google.fr-FR-Standard-B", "Google.fr-FR-Standard-C", "Google.fr-FR-Standard-D", "Google.fr-FR-Standard-E", "Google.fr-FR-Wavenet-A", "Google.fr-FR-Wavenet-B", "Google.fr-FR-Wavenet-C", "Google.fr-FR-Wavenet-D", "Google.fr-FR-Wavenet-E", "Google.fr-FR-Neural2-A", "Google.fr-FR-Neural2-B", "Google.fr-FR-Neural2-C", "Google.fr-FR-Neural2-D", "Google.fr-FR-Neural2-E", "Google.gl-ES-Standard-A", "Polly.Hannah-Neural", "Polly.Hans", "Polly.Marlene", "Polly.Vicki", "Polly.Vicki-Neural", "Polly.Daniel-Neural", "Google.de-DE-Standard-A", "Google.de-DE-Standard-B", "Google.de-DE-Standard-C", "Google.de-DE-Standard-D", "Google.de-DE-Standard-E", "Google.de-DE-Standard-F", "Google.de-DE-Wavenet-A", "Google.de-DE-Wavenet-B", "Google.de-DE-Wavenet-C", "Google.de-DE-Wavenet-D", "Google.de-DE-Wavenet-E", "Google.de-DE-Wavenet-F", "Google.de-DE-Neural2-A", "Google.de-DE-Neural2-B", "Google.de-DE-Neural2-C", "Google.de-DE-Neural2-D", "Google.de-DE-Neural2-F", "Google.el-GR-Standard-A", "Google.el-GR-Wavenet-A", "Google.gu-IN-Standard-C", "Google.gu-IN-Standard-D", "Google.gu-IN-Wavenet-C", "Google.gu-IN-Wavenet-D", "Google.he-IL-Standard-A", "Google.he-IL-Standard-B", "Google.he-IL-Standard-C", "Google.he-IL-Standard-D", "Google.he-IL-Wavenet-A", "Google.he-IL-Wavenet-B", "Google.he-IL-Wavenet-C", "Google.he-IL-Wavenet-D", "Polly.Aditi", "Polly.Kajal-Neural", "Google.hi-IN-Standard-A", "Google.hi-IN-Standard-B", "Google.hi-IN-Standard-C", "Google.hi-IN-Standard-D", "Google.hi-IN-Wavenet-A", "Google.hi-IN-Wavenet-B", "Google.hi-IN-Wavenet-C", "Google.hi-IN-Wavenet-D", "Google.hi-IN-Neural2-A", "Google.hi-IN-Neural2-B", "Google.hi-IN-Neural2-C", "Google.hi-IN-Neural2-D", "Google.hu-HU-Standard-A", "Google.hu-HU-Wavenet-A", "Polly.Dóra/Polly.Dora", "Polly.Karl", "Google.is-IS-Standard-A", "Google.id-ID-Standard-A", "Google.id-ID-Standard-B", "Google.id-ID-Standard-C", "Google.id-ID-Standard-D", "Google.id-ID-Wavenet-A", "Google.id-ID-Wavenet-B", "Google.id-ID-Wavenet-C", "Google.id-ID-Wavenet-D", "Polly.Bianca", "Polly.Carla", "Polly.Giorgio", "Polly.Bianca-Neural", "Polly.Adriano-Neural", "Google.it-IT-Standard-B", "Google.it-IT-Standard-C", "Google.it-IT-Standard-D", "Google.it-IT-Wavenet-B", "Google.it-IT-Wavenet-C", "Google.it-IT-Wavenet-D", "Google.it-IT-Neural2-A", "Google.it-IT-Neural2-C", "Polly.Mizuki", "Polly.Takumi", "Polly.Takumi-Neural", "Polly.Kazuha-Neural", "Polly.Tomoko-Neural", "Google.ja-JP-Standard-B", "Google.ja-JP-Standard-C", "Google.ja-JP-Standard-D", "Google.ja-JP-Wavenet-B", "Google.ja-JP-Wavenet-C", "Google.ja-JP-Wavenet-D", "Google.kn-IN-Standard-C", "Google.kn-IN-Standard-D", "Google.kn-IN-Wavenet-C", "Google.kn-IN-Wavenet-D", "Polly.Seoyeon", "Polly.Seoyeon-Neural", "Google.ko-KR-Standard-A", "Google.ko-KR-Standard-B", "Google.ko-KR-Standard-C", "Google.ko-KR-Standard-D", "Google.ko-KR-Wavenet-A", "Google.ko-KR-Wavenet-B", "Google.ko-KR-Wavenet-C", "Google.ko-KR-Wavenet-D", "Google.ko-KR-Neural2-A", "Google.ko-KR-Neural2-B", "Google.ko-KR-Neural2-C", "Google.lv-LV-Standard-A", "Google.lt-LT-Standard-A", "Google.ms-MY-Standard-A", "Google.ms-MY-Standard-B", "Google.ms-MY-Standard-C", "Google.ms-MY-Standard-D", "Google.ms-MY-Wavenet-A", "Google.ms-MY-Wavenet-B", "Google.ms-MY-Wavenet-C", "Google.ms-MY-Wavenet-D", "Google.ml-IN-Wavenet-C", "Google.ml-IN-Wavenet-D", "Google.mr-IN-Standard-A", "Google.mr-IN-Standard-B", "Google.mr-IN-Standard-C", "Google.mr-IN-Wavenet-A", "Google.mr-IN-Wavenet-B", "Google.mr-IN-Wavenet-C", "Polly.Liv", "Polly.Ida-Neural", "Google.nb-NO-Standard-A", "Google.nb-NO-Standard-B", "Google.nb-NO-Standard-C", "Google.nb-NO-Standard-D", "Google.nb-NO-Standard-E", "Google.nb-NO-Wavenet-A", "Google.nb-NO-Wavenet-B", "Google.nb-NO-Wavenet-C", "Google.nb-NO-Wavenet-D", "Google.nb-NO-Wavenet-E", "Polly.Jacek", "Polly.Jan", "Polly.Ewa", "Polly.Maja", "Polly.Ola-Neural", "Google.pl-PL-Standard-A", "Google.pl-PL-Standard-B", "Google.pl-PL-Standard-C", "Google.pl-PL-Standard-D", "Google.pl-PL-Standard-E", "Google.pl-PL-Wavenet-A", "Google.pl-PL-Wavenet-B", "Google.pl-PL-Wavenet-C", "Google.pl-PL-Wavenet-D", "Google.pl-PL-Wavenet-E", "Polly.Camila", "Polly.Ricardo", "Polly.Vitória/Polly.Vitoria", "Polly.Camila-Neural", "Polly.Vitoria-Neural", "Polly.Thiago-Neural", "Google.pt-BR-Standard-B", "Google.pt-BR-Standard-C", "Google.pt-BR-Wavenet-B", "Google.pt-BR-Wavenet-C", "Google.pt-BR-Neural2-A", "Google.pt-BR-Neural2-B", "Google.pt-BR-Neural2-C", "Polly.Cristiano", "Polly.Inês/Polly.Ines", "Polly.Ines-Neural", "Google.pt-PT-Standard-A", "Google.pt-PT-Standard-B", "Google.pt-PT-Standard-C", "Google.pt-PT-Standard-D", "Google.pt-PT-Wavenet-A", "Google.pt-PT-Wavenet-B", "Google.pt-PT-Wavenet-C", "Google.pt-PT-Wavenet-D", "Google.pa-IN-Standard-A", "Google.pa-IN-Standard-B", "Google.pa-IN-Standard-C", "Google.pa-IN-Standard-D", "Google.pa-IN-Wavenet-A", "Google.pa-IN-Wavenet-B", "Google.pa-IN-Wavenet-C", "Google.pa-IN-Wavenet-D", "Polly.Carmen", "Google.ro-RO-Standard-A", "Google.ro-RO-Wavenet-A", "Polly.Maxim", "Polly.Tatyana", "Google.ru-RU-Standard-A", "Google.ru-RU-Standard-B", "Google.ru-RU-Standard-C", "Google.ru-RU-Standard-D", "Google.ru-RU-Standard-E", "Google.ru-RU-Wavenet-A", "Google.ru-RU-Wavenet-B", "Google.ru-RU-Wavenet-C", "Google.ru-RU-Wavenet-D", "Google.ru-RU-Wavenet-E", "Google.sr-RS-Standard-A", "Google.sk-SK-Standard-A", "Google.sk-SK-Wavenet-A", "Polly.Mia", "Polly.Mia-Neural", "Polly.Andres-Neural", "Polly.Conchita", "Polly.Enrique", "Polly.Lucia", "Polly.Lucia-Neural", "Polly.Sergio-Neural", "Google.es-ES-Standard-B", "Google.es-ES-Standard-C", "Google.es-ES-Standard-D", "Google.es-ES-Wavenet-B", "Google.es-ES-Wavenet-C", "Google.es-ES-Wavenet-D", "Google.es-ES-Neural2-A", "Google.es-ES-Neural2-B", "Google.es-ES-Neural2-C", "Google.es-ES-Neural2-D", "Google.es-ES-Neural2-E", "Google.es-ES-Neural2-F", "man", "woman", "Polly.Lupe", "Polly.Miguel", "Polly.Penélope/Polly.Penelope", "Polly.Lupe-Neural", "Polly.Pedro-Neural", "Google.es-US-Standard-A", "Google.es-US-Standard-B", "Google.es-US-Standard-C", "Google.es-US-Wavenet-A", "Google.es-US-Wavenet-B", "Google.es-US-Wavenet-C", "Google.es-US-Neural2-A", "Google.es-US-Neural2-B", "Google.es-US-Neural2-C", "Polly.Astrid", "Polly.Elin-Neural", "Google.sv-SE-Standard-A", "Google.sv-SE-Standard-B", "Google.sv-SE-Standard-C", "Google.sv-SE-Standard-D", "Google.sv-SE-Standard-E", "Google.sv-SE-Wavenet-A", "Google.sv-SE-Wavenet-B", "Google.sv-SE-Wavenet-C", "Google.sv-SE-Wavenet-D", "Google.sv-SE-Wavenet-E", "Google.ta-IN-Standard-C", "Google.ta-IN-Standard-D", "Google.ta-IN-Wavenet-C", "Google.ta-IN-Wavenet-D", "Google.te-IN-Standard-A", "Google.te-IN-Standard-B", "Google.th-TH-Standard-A", "Polly.Filiz", "Google.tr-TR-Standard-A", "Google.tr-TR-Standard-B", "Google.tr-TR-Standard-C", "Google.tr-TR-Standard-D", "Google.tr-TR-Standard-E", "Google.tr-TR-Wavenet-A", "Google.tr-TR-Wavenet-B", "Google.tr-TR-Wavenet-C", "Google.tr-TR-Wavenet-D", "Google.tr-TR-Wavenet-E", "Google.uk-UA-Standard-A", "Google.uk-UA-Wavenet-A", "Google.vi-VN-Standard-A", "Google.vi-VN-Standard-B", "Google.vi-VN-Standard-C", "Google.vi-VN-Standard-D", "Google.vi-VN-Wavenet-A", "Google.vi-VN-Wavenet-B", "Google.vi-VN-Wavenet-C", "Google.vi-VN-Wavenet-D", "Polly.Gwyneth"}  # fmt:skip
TWILIO_ASR_SUPPORTED_LANGUAGES = ["af-ZA", "am-ET", "hy-AM", "az-AZ", "id-ID", "ms-MY", "bn-BD", "bn-IN", "ca-ES", "cs-CZ", "da-DK", "de-DE", "en-AU", "en-CA", "en-GH", "en-GB", "en-IN", "en-IE", "en-KE", "en-NZ", "en-NG", "en-PH", "en-ZA", "en-TZ", "en-US", "es-AR", "es-BO", "es-CL", "es-CO", "es-CR", "es-EC", "es-SV", "es-ES", "es-US", "es-GT", "es-HN", "es-MX", "es-NI", "es-PA", "es-PY", "es-PE", "es-PR", "es-DO", "es-UY", "es-VE", "eu-ES", "fil-PH", "fr-CA", "fr-FR", "gl-ES", "ka-GE", "gu-IN", "hr-HR", "zu-ZA", "is-IS", "it-IT", "jv-ID", "kn-IN", "km-KH", "lo-LA", "lv-LV", "lt-LT", "hu-HU", "ml-IN", "mr-IN", "nl-NL", "ne-NP", "nb-NO", "pl-PL", "pt-BR", "pt-PT", "ro-RO", "si-LK", "sk-SK", "sl-SI", "su-ID", "sw-TZ", "sw-KE", "fi-FI", "sv-SE", "ta-IN", "ta-SG", "ta-LK", "ta-MY", "te-IN", "vi-VN", "tr-TR", "ur-PK", "ur-IN", "el-GR", "bg-BG", "ru-RU", "sr-RS", "uk-UA", "he-IL", "ar-IL", "ar-JO", "ar-AE", "ar-BH", "ar-DZ", "ar-SA", "ar-IQ", "ar-KW", "ar-MA", "ar-TN", "ar-OM", "ar-PS", "ar-QA", "ar-LB", "ar-EG", "fa-IR", "hi-IN", "th-TH", "ko-KR", "cmn-Hant-TW", "yue-Hant-HK", "ja-JP", "cmn-Hans-HK", "cmn-Hans-CN"]  # fmt: skip

SILENCE_RESPONSE = (
    "Sorry, I didn't get that. Please call again in a more quiet environment."
)

WEBHOOK_ERROR_MSG = "Sorry. This number has been incorrectly configured. Contact the bot integration owner or try again later."

router = APIRouter()


def get_twilio_tts_voice(bi: BotIntegration) -> str:
    from recipes.TextToSpeech import TextToSpeechProviders

    run = bi.get_active_saved_run()
    state: dict = run.state
    tts_provider = state.get("tts_provider")
    if tts_provider and tts_provider == TextToSpeechProviders.GOOGLE_TTS.name:
        voice = "Google." + state.get("google_voice_name", "en-US-Wavenet-F")
        if voice not in TWILIO_SUPPORTED_VOICES:
            logger.warning(f"Unsupported voice {voice=} for {bi=}")
            return DEFAULT_VOICE_NAME
        return voice
    return DEFAULT_VOICE_NAME


def get_twilio_asr_language(bi: BotIntegration) -> str:
    from daras_ai_v2.asr import get_language_match

    run = bi.get_active_saved_run()
    state: dict = run.state

    asr_language = get_language_match(
        state.get("asr_language"), TWILIO_ASR_SUPPORTED_LANGUAGES
    )
    if asr_language:
        return asr_language

    user_language = get_language_match(
        state.get("user_language"), TWILIO_ASR_SUPPORTED_LANGUAGES
    )
    if user_language:
        return user_language

    return DEFAULT_ASR_LANGUAGE


@router.post("/__/twilio/voice/")
def twilio_voice_call(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """Handle incoming Twilio voice call."""

    try:
        bot = TwilioVoice.from_data(data)
    except BotIntegration.DoesNotExist as e:
        logger.debug(f"could not find bot integration for {data=} {e=}")
        resp = VoiceResponse()
        resp.reject()
        return twiml_response(resp)

    bi = bot.bi

    initial_text = bi.twilio_initial_text.strip()
    initial_audio_url = bi.twilio_initial_audio_url.strip()
    if not initial_text and not initial_audio_url:
        initial_text = DEFAULT_INITIAL_TEXT.format(bot_name=bi.name)

    resp = create_voice_call_response(
        bot, text=initial_text, audio_url=initial_audio_url, should_translate=True
    )

    if bi.twilio_use_missed_call:
        background_tasks.add_task(callback_after_missed_call, bot=bot, resp=resp)
        resp = VoiceResponse()
        resp.reject()

    return twiml_response(resp)


def callback_after_missed_call(*, bot: TwilioVoice, resp: VoiceResponse):
    # if data.get("StirVerstat"):
    sleep(1)
    bot.start_voice_call_session(resp)


@router.post("/__/twilio/voice/response/")
def twilio_voice_call_response(
    background_tasks: BackgroundTasks,
    convo_id: str,
    text: str = None,
    audio_url: str = None,
    data: dict = fastapi_request_urlencoded_body,
):
    """Response is ready, user has been dequeued, send the response and ask for the next one."""
    logger.debug(data)
    try:
        convo = Conversation.objects.get(id=int(convo_id))
    except Conversation.DoesNotExist:
        return Response(status_code=404)
    bot = TwilioVoice(convo=convo)
    resp = create_voice_call_response(bot, text=text, audio_url=audio_url)
    background_tasks.add_task(delete_queue, bi=bot.bi, queue_sid=data["QueueSid"][0])
    return twiml_response(resp)


def delete_queue(bi: BotIntegration, queue_sid: str):
    bi.get_twilio_client().queues(queue_sid).delete()


def create_voice_call_response(
    bot: TwilioVoice, *, text: str, audio_url: str, should_translate: bool = False
) -> VoiceResponse:
    resp = VoiceResponse()

    # the URL to send the user's question to
    action = get_api_route_url(twilio_voice_call_asked)

    if bot.use_gooey_asr:
        # record does not support nesting, so we can't support interrupting the response with the next question
        if audio_url:
            resp.play(audio_url)
        elif text:
            resp_say_or_tts_play(bot, resp, text, should_translate=should_translate)

        # try recording 3 times to give the user a chance to start speaking
        resp.record(
            action=action,
            method="POST",
            timeout=5,
            finish_on_key="0",
            play_beep=False,
        )
    else:
        gather = Gather(
            input="speech",  # also supports dtmf (keypad input) and a combination of both
            timeout=20,  # users get 20 to start speaking
            speechTimeout=3,  # a 3 second pause ends the input
            action=action,
            method="POST",
            finish_on_key="0",  # user can press 0 to end the input
            language=get_twilio_asr_language(bot.bi),
            speech_model="phone_call",  # optimized for phone call audio
            enhanced=True,  # only phone_call model supports enhanced
        )

        # by attaching to gather, we allow the user to interrupt with the next question while the response is playing
        if audio_url:
            gather.play(audio_url)
        elif text:
            resp_say_or_tts_play(bot, gather, text, should_translate=should_translate)

        resp.append(gather)

    # if the user doesn't say anything, we'll ask them to call back in a quieter environment
    resp_say_or_tts_play(bot, resp, SILENCE_RESPONSE, should_translate=True)

    return resp


@router.post("/__/twilio/voice/asked/")
def twilio_voice_call_asked(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """After the initial call, the user has asked a question via Twilio/Gooey ASR. Handle their question."""

    bot = TwilioVoice.from_data(data)
    background_tasks.add_task(msg_handler, bot)

    resp = VoiceResponse()
    if bot.input_type == "text":
        resp_say_or_tts_play(
            bot, resp, "I heard " + bot.get_input_text(), should_translate=True
        )
    # send back waiting audio, and wait for the msg_handler to send the response
    resp.enqueue(
        name=bot.twilio_queue.friendly_name,
        wait_url=get_api_route_url(
            twilio_voice_call_wait,
            query_params=dict(audio_url=bot.bi.twilio_waiting_audio_url),
        ),
    )
    return twiml_response(resp)


@router.post("/__/twilio/voice/wait/")
def twilio_voice_call_wait(audio_url: str = None):
    """Play the waiting audio for the user in the queue."""
    resp = VoiceResponse()
    if audio_url:
        audio_urls = [audio_url]
    else:
        random.shuffle(DEFAULT_WAITING_AUDIO_URLS)
        audio_urls = DEFAULT_WAITING_AUDIO_URLS
    for url in audio_urls:
        resp.play(url)
    return twiml_response(resp)


# uncomment for debugging:
@router.post("/__/twilio/voice/status/")
def twilio_voice_call_status(data: dict = fastapi_request_urlencoded_body):
    """Handle incoming Twilio voice call status update."""

    print("Twilio status update", data)

    return Response(status_code=204)


def resp_say_or_tts_play(
    bot: TwilioVoice,
    resp: VoiceResponse | Gather,
    text: str,
    *,
    should_translate: bool = False,
):
    """Say the given text using the bot integration's voice. If the bot integration is set to use Gooey TTS, use that instead."""

    if should_translate:
        text = bot.translate_response(text)

    if bot.use_gooey_tts:
        try:
            # submit the TTS request
            tts_state = TextToSpeechPage.RequestModel.parse_obj(
                {**bot.saved_run.state, "text_prompt": text}
            ).dict()
            result, sr = TextToSpeechPage.get_root_published_run().submit_api_call(
                current_user=AppUser.objects.get(uid=bot.billing_account_uid),
                request_body=tts_state,
            )
            # wait for the TTS to finish
            get_celery_result_db_safe(result)
            sr.refresh_from_db()
            # check for errors
            if sr.error_msg:
                raise RuntimeError(sr.error_msg)
            # play the audio
            resp.play(sr.state["audio_url"])
        except Exception as e:
            traceback.print_exc()
            capture_exception(e)
            # continue with the text if the TTS fails
        else:
            return

    resp.say(text, voice=get_twilio_tts_voice(bot.bi))


@router.post("/__/twilio/voice/error/")
def twilio_voice_call_error():
    """If an unhandled error occurs in the voice call webhook, return a generic error message."""

    resp = VoiceResponse()
    resp.say(WEBHOOK_ERROR_MSG)
    return twiml_response(resp)


@router.post("/__/twilio/sms/")
def twilio_sms(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """Handle incoming Twilio SMS."""
    from daras_ai_v2.twilio_bot import TwilioSMS
    from daras_ai_v2.bots import msg_handler

    bot = TwilioSMS(data)
    background_tasks.add_task(msg_handler, bot)

    resp = MessagingResponse()

    if bot.bi.twilio_waiting_text.strip():
        text = bot.bi.twilio_waiting_text
    else:
        text = "Please wait while we process your request."
    resp.message(bot.translate_response(text))

    return twiml_response(resp)


@router.post("/__/twilio/sms/error/")
def twilio_sms_error():
    """If an unhandled error occurs in the SMS webhook, return a generic error message."""

    resp = MessagingResponse()
    resp.message(WEBHOOK_ERROR_MSG)
    return twiml_response(resp)


def twiml_response(twiml: TwiML) -> Response:
    xml = str(twiml)
    logger.debug(xml)
    return Response(xml, headers={"Content-Type": "text/xml"})
