import typing
import requests
import json
from enum import Enum

import gooey_ui as st
from daras_ai_v2.functional import map_parallel

ISO_639_LANGUAGES = {
    "aar": "Afar",
    "abk": "Abkhazian",
    "afr": "Afrikaans",
    "aka": "Akan",
    "alb": "Albanian",
    "amh": "Amharic",
    "ara": "Arabic",
    "arg": "Aragonese",
    "arm": "Armenian",
    "asm": "Assamese",
    "ava": "Avaric",
    "ave": "Avestan",
    "aym": "Aymara",
    "aze": "Azerbaijani",
    "bak": "Bashkir",
    "bam": "Bambara",
    "baq": "Basque",
    "bel": "Belarusian",
    "ben": "Bengali",
    "bho": "Bhojpuri",
    "bih": "Bihari languages",
    "bis": "Bislama",
    "bos": "Bosnian",
    "bre": "Breton",
    "bul": "Bulgarian",
    "bur": "Burmese",
    "cat": "Catalan; Valencian",
    "cha": "Chamorro",
    "che": "Chechen",
    "chi": "Chinese",
    "chu": "Church Slavic; Old Slavonic; Church Slavonic; Old Bulgarian; Old Church Slavonic",
    "chv": "Chuvash",
    "cor": "Cornish",
    "cos": "Corsican",
    "cre": "Cree",
    "cze": "Czech",
    "dan": "Danish",
    "div": "Divehi; Dhivehi; Maldivian",
    "dut": "Dutch; Flemish",
    "dzo": "Dzongkha",
    "eng": "English",
    "epo": "Esperanto",
    "est": "Estonian",
    "ewe": "Ewe",
    "fao": "Faroese",
    "fij": "Fijian",
    "fin": "Finnish",
    "fre": "French",
    "fry": "Western Frisian",
    "ful": "Fulah",
    "geo": "Georgian",
    "ger": "German",
    "gla": "Gaelic; Scottish Gaelic",
    "gle": "Irish",
    "glg": "Galician",
    "glv": "Manx",
    "gre": "Greek, Modern (1453-)",
    "grn": "Guarani",
    "guj": "Gujarati",
    "hat": "Haitian; Haitian Creole",
    "hau": "Hausa",
    "heb": "Hebrew",
    "her": "Herero",
    "hin": "Hindi",
    "hmo": "Hiri Motu",
    "hrv": "Croatian",
    "hun": "Hungarian",
    "ibo": "Igbo",
    "ice": "Icelandic",
    "ido": "Ido",
    "iii": "Sichuan Yi; Nuosu",
    "iku": "Inuktitut",
    "ile": "Interlingue; Occidental",
    "ina": "Interlingua (International Auxiliary Language Association)",
    "ind": "Indonesian",
    "ipk": "Inupiaq",
    "ita": "Italian",
    "jav": "Javanese",
    "jpn": "Japanese",
    "kal": "Kalaallisut; Greenlandic",
    "kan": "Kannada",
    "kas": "Kashmiri",
    "kau": "Kanuri",
    "kaz": "Kazakh",
    "khm": "Central Khmer",
    "kik": "Kikuyu; Gikuyu",
    "kin": "Kinyarwanda",
    "kir": "Kirghiz; Kyrgyz",
    "kom": "Komi",
    "kon": "Kongo",
    "kor": "Korean",
    "kua": "Kuanyama; Kwanyama",
    "kur": "Kurdish",
    "lao": "Lao",
    "lat": "Latin",
    "lav": "Latvian",
    "lim": "Limburgan; Limburger; Limburgish",
    "lin": "Lingala",
    "lit": "Lithuanian",
    "ltz": "Luxembourgish; Letzeburgesch",
    "lub": "Luba-Katanga",
    "lug": "Ganda",
    "mac": "Macedonian",
    "mah": "Marshallese",
    "mal": "Malayalam",
    "mao": "Maori",
    "mar": "Marathi",
    "may": "Malay",
    "mlg": "Malagasy",
    "mlt": "Maltese",
    "mon": "Mongolian",
    "nau": "Nauru",
    "nav": "Navajo; Navaho",
    "nbl": "Ndebele, South; South Ndebele",
    "nde": "Ndebele, North; North Ndebele",
    "ndo": "Ndonga",
    "nep": "Nepali",
    "nno": "Norwegian Nynorsk; Nynorsk, Norwegian",
    "nob": "Bokmål, Norwegian; Norwegian Bokmål",
    "nor": "Norwegian",
    "nya": "Chichewa; Chewa; Nyanja",
    "oci": "Occitan (post 1500)",
    "oji": "Ojibwa",
    "ori": "Oriya",
    "orm": "Oromo",
    "oss": "Ossetian; Ossetic",
    "pan": "Panjabi; Punjabi",
    "per": "Persian",
    "pli": "Pali",
    "pol": "Polish",
    "por": "Portuguese",
    "pus": "Pushto; Pashto",
    "que": "Quechua",
    "roh": "Romansh",
    "rum": "Romanian; Moldavian; Moldovan",
    "run": "Rundi",
    "rus": "Russian",
    "sag": "Sango",
    "san": "Sanskrit",
    "sin": "Sinhala; Sinhalese",
    "slo": "Slovak",
    "slv": "Slovenian",
    "sme": "Northern Sami",
    "smo": "Samoan",
    "sna": "Shona",
    "snd": "Sindhi",
    "som": "Somali",
    "sot": "Sotho, Southern",
    "spa": "Spanish; Castilian",
    "srd": "Sardinian",
    "srp": "Serbian",
    "ssw": "Swati",
    "sun": "Sundanese",
    "swa": "Swahili",
    "swe": "Swedish",
    "tah": "Tahitian",
    "tam": "Tamil",
    "tat": "Tatar",
    "tel": "Telugu",
    "tgk": "Tajik",
    "tgl": "Tagalog",
    "tha": "Thai",
    "tib": "Tibetan",
    "tir": "Tigrinya",
    "ton": "Tonga (Tonga Islands)",
    "tsn": "Tswana",
    "tso": "Tsonga",
    "tuk": "Turkmen",
    "tur": "Turkish",
    "twi": "Twi",
    "uig": "Uighur; Uyghur",
    "ukr": "Ukrainian",
    "urd": "Urdu",
    "uzb": "Uzbek",
    "ven": "Venda",
    "vie": "Vietnamese",
    "vol": "Volapük",
    "wel": "Welsh",
    "wln": "Walloon",
    "wol": "Wolof",
    "xho": "Xhosa",
    "yid": "Yiddish",
    "yor": "Yoruba",
    "zha": "Zhuang; Chuang",
    "zul": "Zulu",
    "ab": "Abkhaz",
    "ace": "ace",
    "acm": "acm",
    "acq": "acq",
    "ae": "Avestan",
    "aeb": "aeb",
    "aa": "Afar",
    "af": "Afrikaans",
    "ajp": "ajp",
    "ak": "Akan",
    "sq": "Albanian",
    "am": "Amharic",
    "ar": "Arabic",
    "an": "Aragonese",
    "ary": "ary",
    "arz": "arz",
    "as": "Assamese",
    "ast": "Asturian",
    "av": "Avaric",
    "awa": "awa",
    "ay": "Aymara",
    "az": "Azerbaijani",
    "azb": "azb",
    "ba": "Bashkir",
    "ban": "Balinese",
    "be": "Belarusian",
    "bem": "Bemba",
    "bg": "Bulgarian",
    "bh": "Bihari",
    "bi": "Bislama",
    "bjn": "bjn",
    "bm": "Bambara",
    "bn": "Bengali",
    "bo": "Tibetan",
    "brx": "brx",
    "bs": "Bosnian",
    "bug": "bug",
    "ca": "Catalan",
    "ce": "Chechen",
    "ceb": "Cebuano",
    "cjk": "cjk",
    "ckb": "Central Kurdish",
    "crh": "crh",
    "cs": "Czech",
    "ch": "Chamorro",
    "cv": "Chuvash",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "din": "din",
    "doi": "doi",
    "dyu": "dyu",
    "dz": "Dzongkha",
    "ee": "Ewe",
    "el": "Greek, Modern",
    "en": "English",
    "eo": "Esperanto",
    "es": "Spanish; Castilian",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "ff": "Fula",
    "fi": "Finnish",
    "fj": "Fijian",
    "fo": "Faroese",
    "fon": "fon",
    "fr": "French",
    "fur": "fur",
    "ga": "Irish",
    "gd": "Scottish Gaelic",
    "gl": "Galician",
    "gn": "Guaraní",
    "gom": "gom",
    "gu": "Gujarati",
    "ha": "Hausa",
    "he": "Hebrew (modern)",
    "hi": "Hindi",
    "hne": "hne",
    "hr": "Croatian",
    "ht": "Haitian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "ig": "Igbo",
    "ilo": "ilo",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "jv": "Javanese",
    "ka": "Georgian",
    "kab": "kab",
    "kac": "kac",
    "kam": "kam",
    "kbp": "kbp",
    "kea": "kea",
    "kg": "Kongo",
    "ki": "Kikuyu, Gikuyu",
    "kk": "Kazakh",
    "km": "Khmer",
    "kmb": "kmb",
    "kn": "Kannada",
    "knc": "kr",
    "ko": "Korean",
    "ks": "Kashmiri",
    "ku": "Kurdish",
    "kw": "Cornish",
    "ky": "Kirghiz, Kyrgyz",
    "lb": "Luxembourgish",
    "lg": "Luganda",
    "li": "Limburgish",
    "lij": "lij",
    "lmo": "lmo",
    "ln": "Lingala",
    "lo": "Lao",
    "lt": "Lithuanian",
    "ltg": "ltg",
    "lua": "Luba-Lulua",
    "luo": "luo",
    "lus": "lus",
    "lv": "Latvian",
    "mag": "mag",
    "mai": "mai",
    "mg": "Malagasy",
    "mi": "Māori",
    "min": "min",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mni": "mni",
    "mos": "mos",
    "mr": "Marathi (Marāṭhī)",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Burmese",
    "ne": "Nepali",
    "nl": "Dutch",
    "nn": "Norwegian Nynorsk",
    "no": "Norwegian",
    "nso": "Northern Sotho",
    "nus": "nus",
    "ny": "Nyanja",
    "oc": "Occitan",
    "om": "Oromo",
    "or": "Oriya",
    "pa": "Panjabi, Punjabi",
    "pag": "pag",
    "pap": "pap",
    "pl": "Polish",
    "ps": "Pashto, Pushto",
    "pt": "Portuguese",
    "qu": "Quechua",
    "rn": "Kirundi",
    "ro": "Romanian, Moldavan",
    "ru": "Russian",
    "rw": "Kinyarwanda",
    "sa": "Sanskrit (Saṁskṛta)",
    "sat": "sat",
    "sc": "Sardinian",
    "scn": "scn",
    "sd": "Sindhi",
    "sg": "Sango",
    "shn": "shn",
    "si": "Sinhala, Sinhalese",
    "sk": "Slovak",
    "sl": "Slovene",
    "sm": "Samoan",
    "sn": "Shona",
    "so": "Somali",
    "sr": "Serbian",
    "ss": "Swati",
    "st": "Southern Sotho",
    "su": "Sundanese",
    "sv": "Swedish",
    "sw": "Swahili",
    "szl": "szl",
    "ta": "Tamil",
    "taq": "taq",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "ti": "Tigrinya",
    "tk": "Turkmen",
    "tl": "Tagalog",
    "tn": "Tswana",
    "tpi": "tpi",
    "tr": "Turkish",
    "ts": "Tsonga",
    "tt": "Tatar",
    "tum": "Tumbuka",
    "tw": "Twi",
    "tzm": "tzm",
    "ug": "Uighur, Uyghur",
    "uk": "Ukrainian",
    "umb": "umb",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vec": "vec",
    "vi": "Vietnamese",
    "war": "war",
    "wo": "Wolof",
    "xh": "Xhosa",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "zh": "Chinese",
    "zu": "Zulu",
    "co": "Corsican",
    "cr": "Cree",
    "dv": "Divehi; Maldivian;",
    "hz": "Herero",
    "ho": "Hiri Motu",
    "ia": "Interlingua",
    "ie": "Interlingue",
    "ik": "Inupiaq",
    "io": "Ido",
    "iu": "Inuktitut",
    "kl": "Kalaallisut",
    "kr": "Kanuri",
    "kv": "Komi",
    "kj": "Kwanyama, Kuanyama",
    "la": "Latin",
    "lu": "Luba-Katanga",
    "gv": "Manx",
    "mh": "Marshallese",
    "na": "Nauru",
    "nv": "Navajo, Navaho",
    "nb": "Norwegian Bokmål",
    "nd": "North Ndebele",
    "ng": "Ndonga",
    "ii": "Nuosu",
    "nr": "South Ndebele",
    "oj": "Ojibwe, Ojibwa",
    "cu": "Old Church Slavonic",
    "os": "Ossetian, Ossetic",
    "pi": "Pāli",
    "rm": "Romansh",
    "se": "Northern Sami",
    "to": "Tonga",
    "ty": "Tahitian",
    "ve": "Venda",
    "vo": "Volapük",
    "wa": "Walloon",
    "fy": "Western Frisian",
    "za": "Zhuang, Chuang",
}
TRANSLITERATION_SUPPORTED = ["ar", "bn", " gu", "hi", "ja", "kn", "ru", "ta", "te"]
ROMANIZATION_SUPPORTED = [
    "ar",
    "am",
    "bn",
    "be",
    "hi",
    "ja",
    "uk",
    "ru",
    "sr",
    "uk",
]


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
    languages = google_translate_languages()
    translate_language_selector(languages, label, key)


@st.cache_data()
def google_translate_languages() -> dict[str, str]:
    """
    Get list of supported languages for Google Translate.
    :return: Dictionary of language codes and display names.
    """
    from google.cloud import translate

    parent = f"projects/dara-c1b52/locations/global"
    client = translate.TranslationServiceClient()
    supported_languages = client.get_supported_languages(
        parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_target
    }


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
    from google.cloud import translate_v2

    translate_client = translate_v2.Client()
    result = translate_client.translate(
        texts,
        source_language=source_language,
        target_language=target_language,
        format_="text",
    )
    return [r["translatedText"] for r in result]


def MinT_translate_language_selector(
    label="""
    ###### MinT Translate (*optional*)
    """,
    key="MinT_translate_target",
):
    """
    Streamlit widget for selecting a language for MinT.
    Args:
        label: the label to display
        key: the key to save the selected language to in the session state
    """
    languages = MinT_translate_languages()
    translate_language_selector(languages, label, key)


@st.cache_data()
def MinT_translate_languages() -> dict[str, str]:
    """
    Get list of supported languages for MinT.
    :return: Dictionary of language codes and display names.
    """
    res = requests.get("https://translate.wmcloud.org/api/languages")
    res.raise_for_status()
    languages = res.json()

    return {code: ISO_639_LANGUAGES.get(code, code) for code in languages.keys()}


def run_MinT_translate(
    texts: list[str], translate_target: str, translate_from: str | None = None
) -> list[str]:
    """
    Translate text using the MinT API.
    Args:
        texts (list[str]): Text to be translated.
        translate_target (str): Language code to translate to.
    Returns:
        list[str]: Translated text.
    """
    return map_parallel(
        lambda text: run_MinT_translate_one_text(
            text, translate_target, translate_from
        ),
        texts,
    )


def run_MinT_translate_one_text(
    text: str, translate_target: str, translate_from: str | None = None
) -> str:
    if not translate_from or translate_from not in MinT_translate_languages():
        translate_from = detectLanguage(text)
    if translate_from not in MinT_translate_languages():
        raise ValueError(f"MinT does not support translating from {translate_from}.")

    if translate_from == translate_target:
        return text

    res = requests.post(
        f"https://translate.wmcloud.org/api/translate/{translate_from}/{translate_target}",
        {"text": text},
    )
    res.raise_for_status()

    # e.g. {"model":"IndicTrans2_indec_en","sourcelanguage":"hi","targetlanguage":"en","translation":"hello","translationtime":0.8}
    tanslation = res.json()

    return tanslation.get("translation", [])


def detectLanguage(text: str):
    """
    Return the language code of the text.
    """
    from google.cloud import translate_v2 as translate

    translate_client = translate.Client()
    result = translate_client.detect_language(text)
    language_code = result["language"]
    return language_code


class TranslateAPIs(Enum):
    MinT = "MinT"
    google_translate = "Google Translate"
    Auto = "Auto - use recommended API based on language"


translate_apis = {
    TranslateAPIs.MinT.name: {"languages": MinT_translate_languages},
    TranslateAPIs.google_translate.name: {"languages": google_translate_languages},
}


@st.cache_data()
def translate_languages() -> dict[str, str]:
    dict = {}
    for key, val in translate_apis.items():
        if key != TranslateAPIs.Auto.name:
            dict.update(val["languages"]())
    return dict


translate_apis.update({TranslateAPIs.Auto.name: {"languages": translate_languages}})

TRANSLATE_API_TYPE = typing.Literal[tuple(e.name for e in TranslateAPIs)]
LANGUAGE_CODE_TYPE = typing.TypeVar(
    "LANGUAGE_CODE_TYPE",
    bound=typing.Literal[
        tuple(code for code, language in translate_languages().items())
    ],
)


def run_translate(
    texts: list[str],
    translate_target: str,
    api: TRANSLATE_API_TYPE,
    translate_from: str | None = None,
    romanize_translation: bool = False,
) -> list[str]:
    if not api:
        api = st.session_state.get("translate_api")
    try:
        if api == TranslateAPIs.MinT.name:
            result = run_MinT_translate(texts, translate_target, translate_from)
        elif api == TranslateAPIs.google_translate.name:
            result = run_google_translate(texts, translate_target, translate_from)
        elif api == TranslateAPIs.Auto.name:
            result = run_google_translate(
                texts, translate_target, translate_from
            )  # TODO
        else:
            result = run_google_translate(
                texts, translate_target, translate_from
            )  # default to Google Translate
    except:
        result = run_google_translate(
            texts, translate_target, translate_from
        )  # fall back on Google Translate
    return romanize(result, translate_target) if romanize_translation else result


def translate_api_selector(
    label="###### Translate API",
    key="translate_api",
    allow_none=True,
):
    options = [item.name for item in TranslateAPIs]
    if allow_none:
        options.insert(0, None)
        label += " (*optional*)"
    st.selectbox(
        label=label,
        key=key,
        format_func=lambda k: TranslateAPIs.__getattribute__(TranslateAPIs, k).value
        if k
        else "———",
        options=options,
    )


def translate_language_selector(
    languages: dict[str, str] = None,
    label="###### Translate Target Language",
    key="translate_target",
    api_key="translate_api",
    allow_none=True,
):
    """
    Streamlit widget for selecting a language.
    Args:
        languages: dict mapping language codes to display names
        label: the label to display
        key: the key to save the selected language to in the session state
    """
    if not languages:
        languages = translate_apis[
            st.session_state.get(api_key) or TranslateAPIs.google_translate.name
        ]["languages"]()
    options = list(languages.keys())
    if allow_none:
        options.insert(0, None)
        label += " (*optional*)"
    st.selectbox(
        label=label,
        key=key,
        format_func=lambda k: languages[k] if k else "———",
        options=options,
    )


def translate_settings(
    require_api=False,
    key_apiselect="translate_api",
    require_target=False,
    key_target="translate_target",
    require_source=False,
    key_source="translate_source",
):
    translate_api_selector(key=key_apiselect, allow_none=not require_api)
    translate_language_selector(
        label="###### Input Language",
        key=key_source,
        api_key=key_apiselect,
        allow_none=not require_source,
    )
    translate_language_selector(
        key=key_target, api_key=key_apiselect, allow_none=not require_target
    )


def translate_advanced_settings():
    st.checkbox(
        """
        Enable Transliteration
        """,
        key="enable_transliteration",
    )
    st.caption(
        "Detects romanized input text and transliterates it to non-Latin characters where neccessary (and supported) before passing it to the translation models."
    )
    st.checkbox(
        """
        Romanize Translation
        """,
        key="romanize_translation",
    )
    st.caption(
        """
        After translation, romanize non-Latin characters when supported.

        See [Romanization/Transliteration](https://guides.library.harvard.edu/mideast/romanization#:~:text=Romanization%%20refers%20to%20the%20process,converting%%20one%%20script%%20into%%20another.)
        """
    )


def romanize(texts: list[str], language: LANGUAGE_CODE_TYPE) -> list[str]:
    if language not in ROMANIZATION_SUPPORTED:
        raise ValueError("Romanization not supported for this language")

    import google.auth
    import google.auth.transport.requests

    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)

    res = requests.post(
        f"https://translate.googleapis.com/v3/projects/{project}/locations/global:romanizeText",
        json.dumps(
            {
                "contents": texts,
                "sourceLanguageCode": language,
            }
        ),
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
    )
    res.raise_for_status()

    return [
        rom.get("romanizedText", text)
        for rom, text in zip(res.json()["romanizations"], texts)
    ]


def transliterate():
    pass
