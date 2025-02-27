from django.utils import timezone
from datetime import timedelta, datetime

from bots.models import Workflow

THRESHOLDS = [
    (timedelta(days=365), "y"),
    (timedelta(days=30), "mo"),
    (timedelta(days=1), "d"),
    (timedelta(hours=1), "h"),
    (timedelta(minutes=1), "m"),
    (timedelta(seconds=3), "s"),
]


def get_relative_time(timestamp: datetime) -> str:
    diff = timezone.now() - timestamp

    if abs(diff) < timedelta(seconds=3):
        return "Just now"

    for threshold, unit in THRESHOLDS:
        if abs(diff) >= threshold:
            value = round(diff / threshold)
            return (
                f"{value}{unit} ago" if diff > timedelta() else f"in {abs(value)}{unit}"
            )

    return "Just now"


def get_workflow_emoji(workflow: Workflow) -> str:
    match workflow:
        case 1:  # DOC_SEARCH
            return "🔍"
        case 2:  # DOC_SUMMARY
            return "📚"
        case 3:  # GOOGLE_GPT
            return "🌐"
        case 4:  # VIDEO_BOTS
            return "💬"
        case 5:  # LIPSYNC_TTS
            return "👄"
        case 6:  # TEXT_TO_SPEECH
            return "🗣️"
        case 7:  # ASR (Speech Recognition)
            return "👂🏼"
        case 8:  # LIPSYNC
            return "👄"
        case 9:  # DEFORUM_SD (Deforum Animation)
            return "🎞️"
        case 10:  # COMPARE_TEXT2IMG
            return "🌄"
        case 11:  # TEXT_2_AUDIO
            return "🎵"
        case 12:  # IMG_2_IMG
            return "🖼️"
        case 13:  # FACE_INPAINTING
            return "🖌️"
        case 14:  # GOOGLE_IMAGE_GEN
            return "🖼️"
        case 15:  # COMPARE_UPSCALER
            return "🌄"
        case 16:  # SEO_SUMMARY
            return "🙋🏽‍♀️"
        case 17:  # EMAIL_FACE_INPAINTING
            return "📧"
        case 18:  # SOCIAL_LOOKUP_EMAIL
            return "✍️"
        case 19:  # OBJECT_INPAINTING
            return "🖌️"
        case 20:  # IMAGE_SEGMENTATION
            return "🖼️"
        case 21:  # COMPARE_LLM
            return "⚖️"
        case 22:  # CHYRON_PLANT
            return "🌱"
        case 23:  # LETTER_WRITER
            return "✉️"
        case 24:  # SMART_GPT
            return "💡"
        case 25:  # QR_CODE
            return "🏁"
        case 26:  # DOC_EXTRACT
            return "📄"
        case 27:  # RELATED_QNA_MAKER
            return "💬"
        case 28:  # RELATED_QNA_MAKER_DOC
            return "💬"
        case 29:  # EMBEDDINGS
            return "🧠"
        case 30:  # BULK_RUNNER
            return "🦾"
        case 31:  # BULK_EVAL
            return "⚖️"
        case 32:  # FUNCTIONS
            return "🛠️"
        case 33:  # TRANSLATION
            return "🌐"
        case _:
            return "💬"
