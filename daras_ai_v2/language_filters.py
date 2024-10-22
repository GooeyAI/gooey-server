import typing

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


def are_languages_same(tag1: str, tag2: str) -> bool:
    import langcodes

    """
    Check if two language codes represent the same language.
    """
    try:
        return (
            langcodes.Language.get(tag1).language
            == langcodes.Language.get(tag2).language
        )
    except langcodes.LanguageTagError:
        return False


def normalised_lang_in_collection(tag: str, collection: typing.Iterable[str]) -> str:
    import langcodes

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
