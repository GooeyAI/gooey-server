import typing
import json
from enum import Enum

import gooey_ui as st
from daras_ai_v2.functional import map_parallel
from abc import ABC, abstractmethod

GOOGLE_V3_ENDPOINT = "https://translate.googleapis.com/v3/projects/"


class Translator(ABC):
    # enum name - should be alphanumeric (no spaces or special characters)
    name: str = "Translator"
    # enum value and display name - can be anything
    value: str = "translator"
    description: str = "A translator"
    _can_transliterate: list[str] = {}

    @classmethod
    @abstractmethod
    def detect_languages(cls, texts: list[str]) -> list[str]:
        pass

    @classmethod
    def parse_detected_language(cls, language_code: str):
        is_romanized = language_code.endswith("-Latn")
        language_code = language_code.replace("-Latn", "")
        return is_romanized, language_code

    @classmethod
    @abstractmethod
    def supported_languages(cls) -> dict[str, str]:
        pass

    @classmethod
    def translate(
        cls,
        texts: list[str],
        target_language: str,
        source_language: str | None = None,
        enable_transliteration: bool = True,
    ) -> list[str]:
        # prevent incorrect API calls
        if source_language == target_language:
            return texts

        # detect languages and romanization information if not provided
        if not source_language:
            language_codes = cls.detect_languages(texts)
        elif not enable_transliteration:
            language_codes = [source_language] * len(texts)
        else:  # transliteration is enabled and we are provided a source language
            is_specified_as_romanized, _ = cls.parse_detected_language(source_language)
            if is_specified_as_romanized:
                language_codes = [source_language] * len(texts)
            else:  # check whether it is romanized
                language_codes = cls.detect_languages(texts)

        return map_parallel(
            lambda text, source: cls._translate_text(
                text, source, target_language, enable_transliteration
            ),
            texts,
            language_codes,
        )

    @classmethod
    @abstractmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
    ) -> str:
        pass

    @classmethod
    def language_selector(
        cls,
        label: str = "###### Translate To",
        key: str = "target_language",
        allow_none=True,
    ):
        languages = cls.supported_languages()
        TranslateUI.translate_language_selector(
            languages,
            label=label,
            key=key,
            allow_none=allow_none,
        )


# declared separately for caching since python support for caching classmethods is limited
@st.cache_data()
def _Google_supported_languages() -> dict[str, str]:
    from google.cloud import translate

    parent = f"projects/dara-c1b52/locations/global"
    client = translate.TranslationServiceClient()
    supported_languages = client.get_supported_languages(
        parent=parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_target
    }


class GoogleTranslate(Translator):
    name = "GoogleTranslate"
    value = "Google Translate"
    description = "We call the latest Google Translate API which leverages Google's neural machine translation models (https://en.wikipedia.org/wiki/Google_Neural_Machine_Translation)"
    _can_transliterate = {
        "ar",
        "bn",
        "gu",
        "hi",
        "ja",
        "kn",
        "ru",
        "ta",
        "te",
    }
    _session = None

    @classmethod
    def get_google_auth_session(cls):
        """Gets a session with Google Cloud authentication which takes care of refreshing the token and adding it to request headers."""
        if cls._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            creds, project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            cls._session = AuthorizedSession(credentials=creds), project

        return cls._session

    @classmethod
    def detect_languages(cls, texts: list[str]) -> list[str]:
        from google.cloud import translate_v2

        translate_client = translate_v2.Client()
        detections = translate_client.detect_language(texts)
        return [detection["language"] for detection in detections]

    @classmethod
    def supported_languages(cls) -> dict[str, str]:
        return _Google_supported_languages()

    @classmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
    ):
        is_romanized, source_language = cls.parse_detected_language(source_language)
        enable_transliteration = (
            is_romanized
            and enable_transliteration
            and source_language in cls._can_transliterate
        )
        # prevent incorrect API calls
        if source_language == target_language:
            return text

        authed_session, project = cls.get_google_auth_session()
        res = authed_session.post(
            f"{GOOGLE_V3_ENDPOINT}{project}/locations/global:translateText",
            json.dumps(
                {
                    "source_language_code": source_language,
                    "target_language_code": target_language,
                    "contents": text,
                    "mime_type": "text/plain",
                    "transliteration_config": {
                        "enable_transliteration": enable_transliteration
                    },
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        res.raise_for_status()
        data = res.json()
        result = data["translations"][0]

        return result["translatedText"]


# add new apis to this list:
_all_apis: list[Translator] = [GoogleTranslate]


@st.cache_data()
def _all_languages() -> dict[str, str]:
    dict = {}
    for api in _all_apis:
        dict.update(api.supported_languages())
    return dict


# Types that show up nicely in API docs
TRANSLATE_API_TYPE = typing.TypeVar(
    "TRANSLATE_API_TYPE", bound=typing.Literal[tuple(api.name for api in _all_apis)]
)
LANGUAGE_CODE_TYPE = typing.TypeVar(
    "LANGUAGE_CODE_TYPE",
    bound=typing.Literal[tuple(code for code, _ in _all_languages().items())],
)


class Translate:
    apis: dict[TRANSLATE_API_TYPE, Translator] = {api.name: api for api in _all_apis}
    APIs = APIs = Enum("APIs", {api.name: api.value for api in _all_apis})

    @classmethod
    def detect_languages(
        cls, texts: list[str], api: TRANSLATE_API_TYPE | None = None
    ) -> list[str]:
        return cls.apis.get(api, GoogleTranslate).detect_languages(texts)

    @classmethod
    def run(
        cls,
        texts: list[str],
        target_language: str,
        api: TRANSLATE_API_TYPE = None,
        source_language: str | None = None,
        enable_transliteration: bool = True,
    ) -> list[str]:
        translator = cls.apis.get(api, GoogleTranslate)
        return translator.translate(
            texts, target_language, source_language, enable_transliteration
        )


class TranslateUI:
    @staticmethod
    def translate_api_selector(
        label="###### Translate API",
        key="translate_api",
        allow_none=True,
    ) -> Translator:
        options = list(Translate.apis.keys())
        if allow_none:
            options.insert(0, None)
            label += " (_optional_)"
        selected_api = st.selectbox(
            label=label,
            key=key,
            format_func=lambda k: Translate.apis.get(k).value
            if k and k in Translate.apis
            else "———",
            options=options,
        )
        translator = Translate.apis.get(selected_api)
        if translator:
            st.caption(translator.description)
        return translator

    @staticmethod
    def translate_language_selector(
        languages: dict[str, str] = None,
        label="###### Translate To",
        key="target_language",
        key_apiselect="translate_api",
        allow_none=True,
    ):
        if not languages:
            languages = Translate.apis.get(
                st.session_state.get(key_apiselect), GoogleTranslate
            ).supported_languages()
        options = list(languages.keys())
        if allow_none:
            options.insert(0, None)
            label += " (_optional_)"
        return st.selectbox(
            label=label,
            key=key,
            format_func=lambda k: languages[k] if k else "———",
            options=options,
        )
