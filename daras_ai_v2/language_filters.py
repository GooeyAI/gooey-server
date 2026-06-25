import typing

import gooey_gui as gui
import langcodes

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import (
    UserError,
)
from daras_ai_v2.functional import flatten
from daras_ai_v2.redis_cache import redis_cache_decorator

T = typing.TypeVar("T")


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def translation_languages_without_dialects() -> list[str]:
    from daras_ai_v2.asr import TranslationModels

    return sorted(
        set(
            lang
            for tag in flatten(TranslationModels.target_languages_by_model().values())
            if (lang := normalized_lang_or_none(tag))
        )
    )


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def asr_languages_without_dialects() -> list[str]:
    from daras_ai_v2.asr import asr_supported_languages

    return sorted(
        set(
            lang
            for tag in flatten(asr_supported_languages.values())
            if (lang := normalized_lang_or_none(tag))
        )
    )


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def tts_languages_without_dialects() -> list[str]:
    from daras_ai_v2.text_to_speech_settings_widgets import (
        tts_supported_languages_by_provider,
    )

    return sorted(
        set(
            lang
            for tag in flatten(tts_supported_languages_by_provider().values())
            if (lang := normalized_lang_or_none(tag))
        )
    )


def sort_language_options(options: list[str | None], sort_by: str | None):
    sort_by = sort_by or "en"
    options.sort(key=lambda tag: tag and are_languages_same(tag, sort_by), reverse=True)


def filter_models_by_language(
    language_filter: str | None,
    supported_languages_by_model: dict[T, typing.Iterable[str]],
) -> list[T]:
    """
    Filter models by language and return them as a list of models.
    """
    if not language_filter:
        return []
    return [
        model
        for model, supported_languages in supported_languages_by_model.items()
        if any(are_languages_same(language_filter, tag) for tag in supported_languages)
    ]


def filter_languages(
    language_filter: str, collection: typing.Iterable[str]
) -> typing.List[str]:
    """
    Returns a list of all matching candidates from the collection whose normalized
    language matches the target language.
    """
    return list(
        filter(
            lambda candidate: are_languages_same(candidate, language_filter),
            collection,
        )
    )


def language_filter_selector(
    *,
    options: list[str],
    label: str = '<i class="fa-sharp-duotone fa-solid fa-bars-filter"></i> &nbsp; Filter by Language',
    key: str = "language_filter",
) -> str | None:
    clear_key = key + ":clear"
    if gui.session_state.pop(clear_key, None):
        gui.session_state[key] = None

    with gui.div(
        className="d-flex flex-column flex-md-row align-items-md-center gap-2"
    ):
        if label:
            with gui.div(className="text-muted flex-shrink-0"):
                gui.caption(label, unsafe_allow_html=True)

        with gui.div(className="d-flex align-items-center w-100 w-md-auto"):
            with gui.div(
                className="flex-grow-1 flex-md-grow-0", style=dict(minWidth="200px")
            ):
                language_filter = gui.selectbox(
                    label="",
                    label_visibility="collapsed",
                    key=key,
                    format_func=lambda tag: lang_format_func(
                        tag, default="All Languages"
                    ),
                    options=options,
                    allow_none=True,
                )

            if language_filter:
                gui.button(
                    '<i class="fa-solid fa-circle-xmark"></i>',
                    type="tertiary",
                    key=clear_key,
                    className="px-2 py-1 ms-1 flex-shrink-0",
                )

    return language_filter


def lang_format_func(tag: str, *, default: str = "Auto Detect") -> str:
    if not tag:
        return default
    try:
        return f"{langcodes.Language.get(tag).display_name()} | {tag}"
    except langcodes.LanguageTagError:
        return tag


def are_languages_same(tag1: str, tag2: str) -> bool:
    """Check if two language codes represent the same language."""
    try:
        return (
            langcodes.Language.get(tag1).language
            == langcodes.Language.get(tag2).language
        )
    except langcodes.LanguageTagError:
        return False


def normalised_lang_in_collection(tag: str, collection: typing.Iterable[str]) -> str:
    if tag in collection:
        return tag

    try:
        target_lang = langcodes.Language.get(tag).language
    except langcodes.LanguageTagError:
        raise UserError(
            f"Invalid language tag: {tag!r} | must be one of {set(collection)}"
        )

    for candidate in collection:
        if normalized_lang_or_none(candidate) == target_lang:
            return candidate

    raise UserError(
        f"Unsupported language tag: {tag!r} | must be one of {set(collection)}"
    )


def normalized_lang_or_none(tag: str | None) -> str | None:
    if not tag:
        return None
    try:
        return langcodes.Language.get(tag).language
    except langcodes.LanguageTagError:
        return None
