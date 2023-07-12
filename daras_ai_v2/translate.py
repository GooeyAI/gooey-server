import typing
import requests
import json
from enum import Enum

import gooey_ui as st
from daras_ai_v2.functional import map_parallel
from abc import ABC, abstractmethod

GOOGLE_V3_ENDPOINT = "https://translate.googleapis.com/v3/projects/"
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
ROMANIZATION_SUPPORTED = {
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
}
TRANSLITERATION_SUPPORTED = {
    "as",
    "bn",
    "gu",
    "hi",
    "mr",
    "ne",
    "or",
    "pa",
    "sa",
    "si",
    "kn",
    "ml",
    "ta",
    "te",
    "bo",
    "lo",
    "my",
    "sat",
    "th",
    "be",
    "bg",
    "ru",
    "sr",
    "uk",
    "ar",
    "fa",
    "ur",
    "ja",
    "ko",
    "yue-hant",
    "zh-hant",
    "zh",
    "am",
    "ti",
    "el",
    "he",
}


class Translator(ABC):
    """Each model/API has its own translator class which keeps things in one place and provides a template for adding more."""

    # enum name
    name: str = "Translator"
    # enum value and display name
    value: str = "translator"
    # transliteration should be done by a different endpoint - Translate.transliterate() - for all languages not in this set
    _can_transliterate: list[str] = {}

    @classmethod
    @abstractmethod
    def detect_languages(cls, texts: list[str]) -> list[str]:
        """
        Return the language codes of the texts.
        """
        pass

    @classmethod
    def detect_language(cls, text: str):
        """
        Return the language code of the text.
        """
        return cls.detect_languages([text])[0]

    @classmethod
    def parse_detected_language(cls, language_code: str):
        """
        Parse the language code to a standard format and return whether it is romanized.
        """
        is_romanized = language_code.endswith("-Latn")
        language_code = language_code.replace("-Latn", "")
        return is_romanized, language_code

    @classmethod
    @abstractmethod
    def supported_languages(cls) -> dict[str, str]:
        """
        Get list of supported languages.
        :return: Dictionary of language codes and display names.
        """
        pass

    @classmethod
    def translate(
        cls,
        texts: list[str],
        target_language: str,
        source_language: str | None = None,
        enable_transliteration: bool = True,
    ) -> list[str]:
        """
        Translate text using the specified API.
        Args:
            texts (list[str]): Text to be translated.
            target_language (str): Language code to translate to.
            source_language (str): Language code to translate from.
            enable_transliteration (bool): Detects romanized input text and transliterates it to non-Latin characters where neccessary (and supported) before passing it to the translation models.
            romanize_translation (bool): After translation, romanize non-Latin characters when supported.
        Returns:
            list[str]: Translated text.
        """

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

        if enable_transliteration:
            # transliterate languages using Translate.transliterate() if they can't be transliterated by the translation API
            for i, (text, language_code) in enumerate(zip(texts, language_codes)):
                is_romanized, language_code = cls.parse_detected_language(language_code)
                if (
                    is_romanized
                    and language_code in TRANSLITERATION_SUPPORTED
                    and language_code not in cls._can_transliterate
                ):
                    texts[i] = Translate.transliterate([text], [language_code])[0]
                    language_codes[i] = language_code

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
        """
        Translate text using the specified API.
        Args:
            text (str): Text to be translated.
            target_language (str): Language code to translate to.
            source_language (str): Language code to translate from.
            enable_transliteration (bool): True iff the translator should transliterate the text before translating it when necessary.
        Returns:
            str: Translated text.
        """
        pass

    @classmethod
    def language_selector(
        cls,
        label: str = "###### Translate Target",
        key: str = "target_language",
        allow_none=True,
    ):
        """
        Streamlit widget for selecting a language.
        Args:
            label: the label to display
            key: the key to save the selected language to in the session state
        """
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
        parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_target
    }


class GoogleTranslate(Translator):
    name = "GoogleTranslate"
    value = "Google Translate"
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
        # prevent incorrect API calls, and transliterate text if the source language is romanized even if it matches the target language
        if source_language == target_language:
            return (
                Translate.transliterate([text], [source_language])[0]
                if enable_transliteration
                else text
            )

        if enable_transliteration:
            authed_session, project = cls.get_google_auth_session()
            res = authed_session.post(
                f"https://translation.googleapis.com/v3/projects/{project}/locations/global:translateText",
                json.dumps(
                    {
                        "source_language_code": source_language,
                        "target_language_code": target_language,
                        "contents": text,
                        "mime_type": "text/plain",
                        "transliteration_config": {"enable_transliteration": True},
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                },
            )
            res.raise_for_status()
            data = res.json()
            result = data["translations"][0]
        else:
            from google.cloud import translate_v2

            translate_client = translate_v2.Client()
            result = translate_client.translate(
                text,
                source_language=source_language,
                target_language=target_language,
                format_="text",
            )

        return result["translatedText"]


# declared separately for caching since python support for caching classmethods is limited
@st.cache_data()
def _MinT_supported_languages() -> dict[str, str]:
    res = requests.get("https://translate.wmcloud.org/api/languages")
    res.raise_for_status()
    languages = res.json()

    return {code: ISO_639_LANGUAGES.get(code, code) for code in languages.keys()}


class MinT(Translator):
    name = "MinT"
    value = "MinT"

    @classmethod
    def detect_languages(cls, texts: list[str]) -> list[str]:
        # won't depend on MinT for language detection
        return GoogleTranslate.detect_languages(texts)

    @classmethod
    def supported_languages(cls) -> dict[str, str]:
        return _MinT_supported_languages()

    @classmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
    ):
        _, source_language = cls.parse_detected_language(source_language)
        # enable_transliteration is ignored because translate() already transliterated text when necessary since _can_transliterate is empty

        # prevent incorrect API calls
        if source_language == target_language:
            return text

        res = requests.post(
            f"https://translate.wmcloud.org/api/translate/{source_language}/{target_language}",
            json.dumps({"text": text}),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        res.raise_for_status()

        # e.g. {"model":"IndicTrans2_indec_en","sourcelanguage":"hi","targetlanguage":"en","translation":"hello","translationtime":0.8}
        tanslation = res.json()

        return tanslation.get("translation", text)


class Auto(Translator):
    name = "Auto"
    value = "Auto - use recommended API based on language"
    _can_transliterate = GoogleTranslate._can_transliterate

    @classmethod
    def detect_languages(cls, texts: list[str]) -> list[str]:
        return GoogleTranslate.detect_languages(texts)

    @classmethod
    def supported_languages(cls) -> dict[str, str]:
        """
        Returns all available languages as a dict mapping language code to display name.
        """
        return _all_languages()

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
            and source_language in TRANSLITERATION_SUPPORTED
        )
        # prevent incorrect API calls, and transliterate text if the source language is romanized even if it matches the target language
        if source_language == target_language:
            return (
                Translate.transliterate([text], [source_language])[0]
                if enable_transliteration
                else text
            )

        if (
            source_language in GoogleTranslate._can_transliterate
            and enable_transliteration
        ):
            return GoogleTranslate._translate_text(
                text, source_language + "-Latn", target_language
            )
        if enable_transliteration:
            text = Translate.transliterate(text)[0]
        if source_language in MinT.supported_languages():
            try:
                return MinT._translate_text(text, source_language, target_language)
            except:
                return GoogleTranslate._translate_text(
                    text, source_language, target_language
                )  # fallback to GoogleTranslate
        elif source_language in GoogleTranslate.supported_languages():
            return GoogleTranslate._translate_text(
                text, source_language, target_language
            )
        else:
            raise ValueError(f"Translation from {source_language} is not supported.")


# add new apis to this list:
_all_apis: list[Translator] = [GoogleTranslate, MinT, Auto]


# and this Enum
class APIs(Enum):
    GoogleTranslate = GoogleTranslate.value
    MinT = MinT.value
    Auto = Auto.value


@st.cache_data()
def _all_languages() -> dict[str, str]:
    dict = {}
    for api in _all_apis:
        if api is not Auto:
            dict.update(api.supported_languages())
    return dict


# ================================ Public API ================================
# This is the methods, enums, and types that should be imported elsewhere

# Types that show up nicely in API docs
TRANSLATE_API_TYPE = typing.TypeVar(
    "TRANSLATE_API_TYPE", bound=typing.Literal[tuple(api.name for api in _all_apis)]
)
LANGUAGE_CODE_TYPE = typing.TypeVar(
    "LANGUAGE_CODE_TYPE",
    bound=typing.Literal[tuple(code for code, _ in _all_languages().items())],
)
ROMANIZATION_SUPPORTED_TYPE = typing.TypeVar(
    "ROMANIZATION_SUPPORTED_TYPE",
    bound=typing.Literal[tuple(code for code in ROMANIZATION_SUPPORTED)],
)
TRANSLITERATION_SUPPORTED_TYPE = typing.TypeVar(
    "TRANSLITERATION_SUPPORTED_TYPE",
    bound=typing.Literal[tuple(code for code in TRANSLITERATION_SUPPORTED)],
)


class Translate:
    apis: dict[TRANSLATE_API_TYPE, Translator] = {api.name: api for api in _all_apis}
    APIs = APIs

    @classmethod
    def supported_languages(cls) -> dict[LANGUAGE_CODE_TYPE, str]:
        return _all_languages()

    @classmethod
    def detect_languages(
        cls, texts: list[str], api: TRANSLATE_API_TYPE | None = None
    ) -> list[str]:
        return cls.apis.get(api, Auto).detect_languages(texts)

    @classmethod
    def run(
        cls,
        texts: list[str],
        target_language: str,
        api: TRANSLATE_API_TYPE = None,
        source_language: str | None = None,
        enable_transliteration: bool = True,
        romanize_translation: bool = False,
    ) -> list[str]:
        translator = cls.apis.get(api, Auto)
        result = translator.translate(
            texts, target_language, source_language, enable_transliteration
        )
        return cls.romanize(result, target_language) if romanize_translation else result

    @classmethod
    def romanize(texts: list[str], language: ROMANIZATION_SUPPORTED_TYPE) -> list[str]:
        if language not in ROMANIZATION_SUPPORTED:
            raise ValueError("Romanization not supported for this language")

        authed_session, project = GoogleTranslate.get_google_auth_session()

        res = authed_session.post(
            f"{GOOGLE_V3_ENDPOINT}{project}/locations/global:romanizeText",
            json.dumps(
                {
                    "contents": texts,
                    "sourceLanguageCode": language,
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        res.raise_for_status()

        return [
            rom.get("romanizedText", text)
            for rom, text in zip(res.json()["romanizations"], texts)
        ]

    @classmethod
    def transliterate(
        cls,
        texts: list[str],
        language_codes: list[TRANSLITERATION_SUPPORTED_TYPE] | None = None,
    ) -> list[str]:
        if not language_codes:
            language_codes = cls.detect_languages(texts)
        language_codes = [code.replace("-Latn", "") for code in language_codes]
        return map_parallel(
            lambda text, code: transliterate_text(text, code),
            texts,
            language_codes,
        )


class TranslateUI:
    @staticmethod
    def translate_api_selector(
        label="###### Translate API",
        key="translate_api",
        allow_none=True,
    ) -> TRANSLATE_API_TYPE:
        options = Translate.apis.keys()
        if allow_none:
            options.insert(0, None)
            label += " (_optional_)"
        return st.selectbox(
            label=label,
            key=key,
            format_func=lambda k: Translate.apis.get(k).name
            if k and k in Translate.apis
            else "———",
            options=options,
        )

    @staticmethod
    def translate_settings(
        require_api=False,
        key_apiselect="translate_api",
        require_target=False,
        key_target="target_language",
        require_source=False,
        key_source="source_language",
    ):
        translator = TranslateUI.translate_api_selector(
            key=key_apiselect, allow_none=not require_api
        )
        translator = Translate.apis.get(translator)
        translator.language_selector(
            label="###### Input Language",
            key=key_source,
            allow_none=not require_source,
        )
        translator.language_selector(key=key_target, allow_none=not require_target)

    @staticmethod
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

    @staticmethod
    def translate_language_selector(
        languages: dict[str, str] = None,
        label="###### Translate Target Language",
        key="target_language",
        key_apiselect="translate_api",
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
            languages = Translate.apis.get(
                st.session_state.get(key_apiselect)
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


# ================================ Transliteration ================================
# Below follows general transliteration code using the deprecated Google API
# since the new API does not support transliteration without translation
# and the new API does not support all languages and scripts that the old API did.
# Per Google's deprecation policy, this API will continue working, it just won't get updated
# with bugfixes and the latest models. See: https://developers.google.com/transliterate/terms
# Mutilated from https://github.com/NarVidhai/Google-Transliterate-API

# Transliteration API endpoints
G_API_DEFAULT = "https://inputtools.google.com/request?text=%s&itc=%s-t-i0&num=%d"
G_API_CHINESE = "https://inputtools.google.com/request?text=%s&itc=%s-t-i0-%s&num=%d"

# These have an extra input_scheme parameter in the API
CHINESE_LANGS = {"yue-hant", "zh", "zh-hant"}

# ISO Language code to numeric script name
LANG2SCRIPT = {
    # Indo-Aryan
    "as": "Bengali-Assamese",
    "bn": "Bengali-Assamese",
    "gu": "Gujarati",
    "hi": "Devanagari",
    "mr": "Devanagari",
    "ne": "Devanagari",
    "or": "Oriya",
    "pa": "Gurmukhi",
    "sa": "Devanagari",
    "si": "Sinhala",
    # Dravidian
    "kn": "Kannada",
    "ml": "Malayalam",
    "ta": "Tamil",
    "te": "Telugu",
    # South-East Asia
    "bo": "Tibetan",
    "lo": "Lao",
    "my": "Burmese",
    "sat": "Ol Chiki",
    "th": "Thai",
    # Cyrllic
    "be": "Greek-Upper",
    "bg": "Greek-Upper",
    "ru": "Greek-Upper",
    "sr": "Greek-Upper",
    "uk": "Greek-Upper",
    # PersoArabic
    "ar": "Central-Arabic",
    "fa": "Eastern-Arabic",
    "ur": "Eastern-Arabic",
    # Chinese family
    "ja": "Chinese",
    "ko": "Chinese",
    "yue-hant": "Chinese",
    "zh-hant": "Chinese",
    "zh": "Chinese",
    # African
    "am": "Geʽez",
    "ti": "Geʽez",
    # More scripts
    "el": "Greek-Lower",
    "he": "Hebrew",
}

EN_NUMERALS = "0123456789"

NATIVE_NUMERALS = {
    # Brahmic scripts
    "Bengali-Assamese": "০১২৩৪৫৬৭৮৯",
    "Burmese": "၀၁၂၃၄၅၆၇၈၉",
    "Devanagari": "०१२३४५६७८९",
    "Gujarati": "૦૧૨૩૪૫૬૭૮૯",
    "Gurmukhi": "੦੧੨੩੪੫੬੭੮੯",
    "Kannada": "೦೧೨೩೪೫೬೭೮೯",
    "Lao": "໐໑໒໓໔໕໖໗໘໙",
    "Malayalam": "൦൧൨൩൪൫൬൭൮൯",
    "Ol Chiki": "᱐᱑᱒᱓᱔᱕᱖᱗᱘᱙",
    "Oriya": "୦୧୨୩୪୫୬୭୮୯",
    "Sinhala": "෦෧෨෩෪෫෬෭෮෯",
    "Tamil": "௦௧௨௩௪௫௬௭௮௯",
    "Telugu": "౦౧౨౩౪౫౬౭౮౯",
    "Thai": "๐๑๒๓๔๕๖๗๘๙",
    "Tibetan": "༠༡༢༣༤༥༦༧༨༩",
    "Hindu-Arabic": EN_NUMERALS,
    # Arabic
    "Eastern-Arabic": "۰۱۲۳۴۵۶۷۸۹",
    "Central-Arabic": "٠١٢٣٤٥٦٧٨٩",
    "Hebrew": "0אבגדהוז‎חט",
    # TODO: Add Macron diacritic on top?
    "Greek-Lower": "0αβγδεϛζηθ",
    "Greek-Upper": "0ΑΒΓΔΕϚΖΗΘ",
    "Geʽez": "0፩፪፫፬፭፮፯፰፱",
    "Chinese": "〇一二三四五六七八九",
}

NUMERAL_MAP = {
    script: str.maketrans({en: l for en, l in zip(EN_NUMERALS, numerals)})
    for script, numerals in NATIVE_NUMERALS.items()
}


def transliterate_numerals(text: str, lang_code: str) -> str:
    """Convert standard Hindu-Arabic numerals in given text to native numerals

    Args:
        text (str): The text in which numeral digits should be transliterated.
        lang_code (str): The target language's ISO639 code

    Returns:
        str: Returns transliterated text with numerals converted to native form.
    """
    if lang_code == "en":
        return text
    return text.translate(NUMERAL_MAP[LANG2SCRIPT[lang_code]])


def transliterate_word(
    word: str, lang_code: str, max_suggestions: int = 6, input_scheme="pinyin"
) -> list:
    """Transliterate a given word to the required language.

    Args:
        word (str): The word to transliterate from Latin/Roman (English) script
        lang_code (str): The target language's ISO639 code
        max_suggestions (int, optional): Maximum number of suggestions to fetch. Defaults to 6.
        input_scheme(str, optional): Romanization scheme (Only for Chinese)

    Returns:
        list: List of suggested transliterations.
    """
    if lang_code in CHINESE_LANGS:
        api_url = G_API_CHINESE % (
            word.lower(),
            lang_code,
            input_scheme,
            max_suggestions,
        )
    else:
        api_url = G_API_DEFAULT % (word.lower(), lang_code, max_suggestions)

    response = requests.get(api_url, allow_redirects=False, timeout=5)
    response.raise_for_status()
    r = json.loads(response.text)
    if "SUCCESS" not in r[0]:
        raise requests.HTTPError(
            "Request failed with status code: %d\nERROR: %s"
            % (response.status_code, response.text),
        )
    return r[1][0][1]


def transliterate_text(
    text: str, lang_code: str, convert_numerals: bool = False
) -> str:
    """Transliterate a given sentence or text to the required language.

    Args:
        text (str): The text to transliterate from Latin/Roman (English) script.
        lang_code (str): The target language's ISO639 code
        convert_numerals (bool): Transliterate numerals. Defaults to False.

    Returns:
        str: Transliterated text.
    """
    try:
        result = []
        for word in text.split():
            result.append(transliterate_word(word, lang_code, 1)[0])
        result = " ".join(result)
        if convert_numerals:
            result = transliterate_numerals(result, lang_code)
        return result
    except:
        return text
