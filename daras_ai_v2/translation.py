import json

import requests
from langcodes import Language

import gooey_ui as st
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.google_auth import get_google_auth_session

TRANSLITERATION_SUPPORTED = {"ar", "bn", " gu", "hi", "ja", "kn", "ru", "ta", "te"}


def google_translate_language_selector(
    label="""
    ###### Google Translate (*optional*)
    """,
    key="google_translate_target",
):
    """
    Streamlit widget for selecting a language for Google Translate.
    Args:
        label: the label to display
        key: the key to save the selected language to in the session state
    """
    languages = dict(
        MinT_translate_languages(), **google_translate_languages()
    )  # merge dicts, favor google translate when there are conflicts
    options = list(languages.keys())
    options.insert(0, None)
    st.selectbox(
        label=label,
        key=key,
        format_func=lambda k: languages[k] if k else "———",
        options=options,
    )


@st.cache_data()
def google_translate_languages() -> dict[str, str]:
    """
    Get list of supported languages for Google Translate.
    :return: Dictionary of language codes and display names.
    """
    from google.cloud import translate

    _, project = get_google_auth_session()
    parent = f"projects/{project}/locations/global"
    client = translate.TranslationServiceClient()
    supported_languages = client.get_supported_languages(
        parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_target
    }


@st.cache_data()
def MinT_translate_languages() -> dict[str, str]:
    """
    Get list of supported languages for MinT.
    :return: Dictionary of language codes and display names.
    """
    res = requests.get("https://translate.wmcloud.org/api/languages")
    res.raise_for_status()
    languages = res.json()
    return {code: Language.get(code).display_name() for code in languages.keys()}


def run_google_translate(
    texts: list[str],
    target_language: str,
    source_language: str = None,
) -> list[str]:
    """
    Translate text using the Google Translate API.
    Args:
        texts (list[str]): Text to be translated.
        target_language (str): Language code to translate to.
        source_language (str): Language code to translate from.
    Returns:
        list[str]: Translated text.
    """
    from google.cloud import translate_v2 as translate

    # if the language supports transliteration, we should check if the script is Latin
    if source_language and source_language not in TRANSLITERATION_SUPPORTED:
        language_codes = [source_language] * len(texts)
    else:
        translate_client = translate.Client()
        detections = translate_client.detect_language(texts)
        language_codes = [detection["language"] for detection in detections]

    return map_parallel(
        lambda text, source: _translate_text(text, source, target_language),
        texts,
        language_codes,
    )


def _translate_text(text: str, source_language: str, target_language: str):
    source_language = Language.get(source_language)
    is_romanized = source_language.script == "Latn"
    source_language = source_language.language
    enable_transliteration = (
        is_romanized and source_language in TRANSLITERATION_SUPPORTED
    )
    # prevent incorrect API calls
    if source_language == target_language or not text:
        return text

    if (
        source_language not in google_translate_languages()
        and source_language in MinT_translate_languages()
    ):
        return _run_mint_translate(text, source_language, target_language)

    authed_session, project = get_google_auth_session()
    res = authed_session.post(
        f"https://translation.googleapis.com/v3/projects/{project}/locations/global:translateText",
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

    return result["translatedText"].strip()


def _run_mint_translate(text: str, source_language: str, target_language: str) -> str:
    source_language = Language.get(source_language).language
    target_language = Language.get(target_language).language
    res = requests.post(
        f"https://translate.wmcloud.org/api/translate/{source_language}/{target_language}",
        json.dumps({"text": text}),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    res.raise_for_status()

    # e.g. {"model":"IndicTrans2_indec_en","sourcelanguage":"hi","targetlanguage":"en","translation":"hello","translationtime":0.8}
    tanslation = res.json()
    return tanslation.get("translation", text)
