import typing
import requests

import gooey_ui as st
from daras_ai_v2.functional import map_parallel

ISO_639_LANGUAGES = {
    "ab": "Abkhaz",
    "aa": "Afar",
    "af": "Afrikaans",
    "ak": "Akan",
    "sq": "Albanian",
    "am": "Amharic",
    "ar": "Arabic",
    "an": "Aragonese",
    "hy": "Armenian",
    "as": "Assamese",
    "av": "Avaric",
    "ae": "Avestan",
    "ay": "Aymara",
    "az": "Azerbaijani",
    "bm": "Bambara",
    "ba": "Bashkir",
    "eu": "Basque",
    "be": "Belarusian",
    "bn": "Bengali",
    "bh": "Bihari",
    "bi": "Bislama",
    "bs": "Bosnian",
    "br": "Breton",
    "bg": "Bulgarian",
    "my": "Burmese",
    "ca": "Catalan; Valencian",
    "ch": "Chamorro",
    "ce": "Chechen",
    "ny": "Chichewa; Chewa; Nyanja",
    "zh": "Chinese",
    "cv": "Chuvash",
    "kw": "Cornish",
    "co": "Corsican",
    "cr": "Cree",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "dv": "Divehi; Maldivian;",
    "nl": "Dutch",
    "dz": "Dzongkha",
    "en": "English",
    "eo": "Esperanto",
    "et": "Estonian",
    "ee": "Ewe",
    "fo": "Faroese",
    "fj": "Fijian",
    "fi": "Finnish",
    "fr": "French",
    "ff": "Fula",
    "gl": "Galician",
    "ka": "Georgian",
    "de": "German",
    "el": "Greek, Modern",
    "gn": "Guaraní",
    "gu": "Gujarati",
    "ht": "Haitian",
    "ha": "Hausa",
    "he": "Hebrew (modern)",
    "hz": "Herero",
    "hi": "Hindi",
    "ho": "Hiri Motu",
    "hu": "Hungarian",
    "ia": "Interlingua",
    "id": "Indonesian",
    "ie": "Interlingue",
    "ga": "Irish",
    "ig": "Igbo",
    "ik": "Inupiaq",
    "io": "Ido",
    "is": "Icelandic",
    "it": "Italian",
    "iu": "Inuktitut",
    "ja": "Japanese",
    "jv": "Javanese",
    "kl": "Kalaallisut",
    "kn": "Kannada",
    "kr": "Kanuri",
    "ks": "Kashmiri",
    "kk": "Kazakh",
    "km": "Khmer",
    "ki": "Kikuyu, Gikuyu",
    "rw": "Kinyarwanda",
    "ky": "Kirghiz, Kyrgyz",
    "kv": "Komi",
    "kg": "Kongo",
    "ko": "Korean",
    "ku": "Kurdish",
    "kj": "Kwanyama, Kuanyama",
    "la": "Latin",
    "lb": "Luxembourgish",
    "lg": "Luganda",
    "li": "Limburgish",
    "ln": "Lingala",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lu": "Luba-Katanga",
    "lv": "Latvian",
    "gv": "Manx",
    "mk": "Macedonian",
    "mg": "Malagasy",
    "ms": "Malay",
    "ml": "Malayalam",
    "mt": "Maltese",
    "mi": "Māori",
    "mr": "Marathi (Marāṭhī)",
    "mh": "Marshallese",
    "mn": "Mongolian",
    "na": "Nauru",
    "nv": "Navajo, Navaho",
    "nb": "Norwegian Bokmål",
    "nd": "North Ndebele",
    "ne": "Nepali",
    "ng": "Ndonga",
    "nn": "Norwegian Nynorsk",
    "no": "Norwegian",
    "ii": "Nuosu",
    "nr": "South Ndebele",
    "oc": "Occitan",
    "oj": "Ojibwe, Ojibwa",
    "cu": "Old Church Slavonic",
    "om": "Oromo",
    "or": "Oriya",
    "os": "Ossetian, Ossetic",
    "pa": "Panjabi, Punjabi",
    "pi": "Pāli",
    "fa": "Persian",
    "pl": "Polish",
    "ps": "Pashto, Pushto",
    "pt": "Portuguese",
    "qu": "Quechua",
    "rm": "Romansh",
    "rn": "Kirundi",
    "ro": "Romanian, Moldavan",
    "ru": "Russian",
    "sa": "Sanskrit (Saṁskṛta)",
    "sc": "Sardinian",
    "sd": "Sindhi",
    "se": "Northern Sami",
    "sm": "Samoan",
    "sg": "Sango",
    "sr": "Serbian",
    "gd": "Scottish Gaelic",
    "sn": "Shona",
    "si": "Sinhala, Sinhalese",
    "sk": "Slovak",
    "sl": "Slovene",
    "so": "Somali",
    "st": "Southern Sotho",
    "es": "Spanish; Castilian",
    "su": "Sundanese",
    "sw": "Swahili",
    "ss": "Swati",
    "sv": "Swedish",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "ti": "Tigrinya",
    "bo": "Tibetan",
    "tk": "Turkmen",
    "tl": "Tagalog",
    "tn": "Tswana",
    "to": "Tonga",
    "tr": "Turkish",
    "ts": "Tsonga",
    "tt": "Tatar",
    "tw": "Twi",
    "ty": "Tahitian",
    "ug": "Uighur, Uyghur",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "ve": "Venda",
    "vi": "Vietnamese",
    "vo": "Volapük",
    "wa": "Walloon",
    "cy": "Welsh",
    "wo": "Wolof",
    "fy": "Western Frisian",
    "xh": "Xhosa",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "za": "Zhuang, Chuang",
    "zu": "Zulu",
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
}
TRANSLITERATION_SUPPORTED = ["ar", "bn", " gu", "hi", "ja", "kn", "ru", "ta", "te"]


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
        translate_from = MinT_detectLanguage(text)

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


def MinT_detectLanguage(text: str):
    """
    Return the language code of the text.
    """
    res = requests.post("https://translate.wmcloud.org/api/detectlang", {"text": text})
    res.raise_for_status()
    detection = res.json()  # e.g. {"language":"en","score":98}
    if detection.get("score", -1) < 50:
        from google.cloud import translate_v2 as translate

        translate_client = translate.Client()
        result = translate_client.detect_language(text)
        score = result["confidence"]
        language_code = result["language"]
        if score < 50 or language_code not in MinT_translate_languages():
            raise ValueError(
                "Not certain enough about language or it is not supported. Raising error to fall back to Google Translate"
            )
        return language_code
    return detection.get("language", "en")


class TranslateAPIs(Enum):
    MinT = "MinT"
    google_translate = "Google Translate"


translate_apis = {
    TranslateAPIs.MinT.name: {"languages": MinT_translate_languages()},
    TranslateAPIs.google_translate.name: {"languages": google_translate_languages()},
}


def run_translate(
    texts: list[str],
    translate_target: str,
    api: typing.Literal[tuple(e.name for e in TranslateAPIs)],
    translate_from: str | None = None,
) -> list[str]:
    if not api:
        api = st.session_state.get("translate_api")
    try:
        if api == TranslateAPIs.MinT.name:
            return run_MinT_translate(texts, translate_target, translate_from)
        elif api == TranslateAPIs.google_translate.name:
            return run_google_translate(texts, translate_target, translate_from)
    except:
        pass
    return run_google_translate(
        texts, translate_target, translate_from
    )  # fall back on Google Translate


def translate_api_selector(
    label="""
    ###### Translate API (*optional*)
    """,
    key="translate_api",
):
    options = [item.name for item in TranslateAPIs]
    options.insert(0, None)
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
    label="""
    ###### Translate (*optional*)
    """,
    key="translate_target",
    api_key="translate_api",
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
        ]["languages"]
    options = list(languages.keys())
    options.insert(0, None)
    st.selectbox(
        label=label,
        key=key,
        format_func=lambda k: languages[k] if k else "———",
        options=options,
    )
