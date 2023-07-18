import typing
import requests
import json
from enum import Enum
from abc import ABC, abstractmethod
import re

import gooey_ui as st
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.redis_cache import redis_cache_decorator

DEFAULT_GLOSSARY_URL = "https://docs.google.com/spreadsheets/d/1IRHKcOC86oZXwMB0hR7eej7YVg5kUHpriZymwYQcQX4/edit?usp=sharing"  # only viewing access
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

    # enum name - should be alphanumeric (no spaces or special characters)
    name: str = "Translator"
    # enum value and display name - can be anything
    value: str = "translator"
    # transliteration should be done by a different endpoint - Translate.transliterate() - for all languages not in this set
    _can_transliterate: list[str] = {}
    # whether the translator supports glossaries, if false, the glossary will be masked out by the translate function manually
    _supports_glossary: bool = False

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
    @abstractmethod
    def description(cls) -> str:
        """
        Get description of the translator.
        :return: Description of the translator.
        """
        pass

    @classmethod
    def translate(
        cls,
        texts: list[str],
        target_language: str,
        source_language: str | None = None,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
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
        # prevent incorrect API calls, and transliterate text if the source language is romanized even if it matches the target language
        if source_language == target_language:
            return (
                Translate.transliterate(texts, [source_language] * len(texts))
                if enable_transliteration
                else texts
            )

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
                    if glossary_url:
                        _, df = _update_or_create_glossary(glossary_url)
                        text, replaced_glossies = _mask_glossary(
                            text, language_code, target_language, df
                        )
                    texts[i] = Translate.transliterate([text], [language_code])[0]
                    if glossary_url:
                        texts[i] = _unmask_glossary(
                            texts[i], replaced_glossies, language_code
                        )
                    language_codes[i] = language_code

        replaced_glossies = [[]] * len(texts)
        if not cls._supports_glossary:
            _, df = _update_or_create_glossary(glossary_url)
            for text, language_code in zip(texts, language_codes):
                text, replaced_gloss = _mask_glossary(
                    text, language_code, target_language, df
                )
                replaced_glossies[i] = list(replaced_gloss)
                texts[i] = text

        return map_parallel(
            lambda text, source, glossies: _unmask_glossary(
                cls._translate_text(
                    text, source, target_language, enable_transliteration, glossary_url
                ),
                glossies,
                target_language,
            ),
            texts,
            language_codes,
            replaced_glossies,
        )

    @classmethod
    @abstractmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
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
        label: str = "###### Translate To",
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
    _supports_glossary = True
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
    def description(cls) -> str:
        return "We call the latest Google Translate API which leverages Google's neural machine translation models (https://en.wikipedia.org/wiki/Google_Neural_Machine_Translation)"

    @classmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
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

        if glossary_url:
            uri, df = _update_or_create_glossary(glossary_url)
            if enable_transliteration:
                # glossary translation doesn't support transliteration, so we patch it in
                enable_transliteration = False
                text, replaced_glossaries = _mask_glossary(
                    text, target_language, source_language, df
                )
                text = Translate.transliterate([text], [source_language])[0]
                text = _unmask_glossary(text, replaced_glossaries, source_language)
            glossary_config = {
                "glossaryConfig": {
                    "glossary": uri,
                    "ignoreCase": True,
                }
            }

        config = {
            "source_language_code": source_language,
            "target_language_code": target_language,
            "contents": text,
            "mime_type": "text/plain",
            "transliteration_config": {
                "enable_transliteration": enable_transliteration
            },
        }
        if glossary_config:
            config.update(glossary_config)

        authed_session, project = cls.get_google_auth_session()
        res = authed_session.post(
            f"{GOOGLE_V3_ENDPOINT}{project}/locations/us-central1:translateText",
            json.dumps(config),
            headers={
                "Content-Type": "application/json",
            },
        )
        res.raise_for_status()
        data = res.json()
        if (
            glossary_url
            and data["glossaryTranslations"]
            and "translatedText" in data["glossaryTranslations"][0]
        ):
            result = data["glossaryTranslations"][0]
        else:
            result = data["translations"][0]

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
    def description(cls) -> str:
        return "MinT by WikiMedia (https://diff.wikimedia.org/2023/06/13/mint-supporting-underserved-languages-with-open-machine-translation/) uses the best translation tools from Meta, AI4Bharat and more."

    @classmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
    ):
        _, source_language = cls.parse_detected_language(source_language)
        # enable_transliteration is ignored because translate() already transliterated text when necessary since _can_transliterate is empty
        # glossary_url is ignored because _supports_glossary is False so the glossary will be masked out by the translate function manually

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
    def description(cls) -> str:
        return "Automatically detects the language(s) and uses the best API for the language."

    @classmethod
    def _translate_text(
        cls,
        text: str,
        source_language: str,
        target_language: str,
        enable_transliteration: bool = True,
        glossary_url: str | None = None,
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
                text,
                source_language + "-Latn",
                target_language,
                glossary_url=glossary_url,
            )
        if enable_transliteration:
            text = Translate.transliterate(text)[0]
        if source_language in MinT.supported_languages():
            try:
                return MinT._translate_text(text, source_language, target_language)
            except:
                return GoogleTranslate._translate_text(
                    text, source_language, target_language, glossary_url=glossary_url
                )  # fallback to GoogleTranslate
        elif source_language in GoogleTranslate.supported_languages():
            return GoogleTranslate._translate_text(
                text, source_language, target_language, glossary_url=glossary_url
            )
        elif source_language == "und":
            # und = undetermined, meaning the language detection failed
            # so we'll run google translate without a source language
            return GoogleTranslate._translate_text(
                text, target_language=target_language, glossary_url=glossary_url
            )
        else:
            raise ValueError(f"Translation from {source_language} is not supported.")


# add new apis to this list:
_all_apis: list[Translator] = [GoogleTranslate, MinT, Auto]


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
    APIs = APIs = Enum("APIs", {api.name: api.value for api in _all_apis})

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
        glossary_url: str | None = DEFAULT_GLOSSARY_URL,
    ) -> list[str]:
        translator = cls.apis.get(api, Auto)
        result = translator.translate(
            texts,
            target_language,
            source_language,
            enable_transliteration,
            glossary_url,
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
            st.caption(translator.description())
        return translator

    @staticmethod
    def translate_settings(
        require_api=False,
        key_apiselect="translate_api",
        require_target=False,
        key_target="target_language",
        require_source=False,
        key_source="source_language",
    ):
        translator = (
            TranslateUI.translate_api_selector(
                key=key_apiselect, allow_none=not require_api
            )
            or Auto
        )
        translator.language_selector(
            label="""
            ###### Input Language
            Automatically detect language if not specified. If this is the same as the target language, transliteration will be applied if enabled, otherwise no translation will take place.
            """,
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
            "Detects romanized input text and transliterates it to non-Latin characters where neccessary (and supported) before passing it to the translation models, e.g. this will turn Namaste into नमस्ते which makes it easier for the translation models to understand."
        )
        st.checkbox(
            """
            Romanize Translation
            """,
            key="romanize_translation",
        )
        st.caption(
            """
            After translation, romanize non-Latin characters when supported, e.g. this will turn नमस्ते into Namaste.

            See [Romanization/Transliteration](https://guides.library.harvard.edu/mideast/romanization#:~:text=Romanization%%20refers%20to%20the%20process,converting%%20one%%20script%%20into%%20another.)
            """
        )
        TranslateUI.translate_glossary_input()

    @staticmethod
    def translate_language_selector(
        languages: dict[str, str] = None,
        label="###### Translate To",
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
                st.session_state.get(key_apiselect), Auto
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

    @staticmethod
    def translate_glossary_input(
        label="##### Glossary\nUpload a google sheet, csv, or xlsx file.",
        key="glossary_url",
    ):
        """
        Streamlit widget for inputting a glossary.
        Args:
            label: the label to display
            key: the key to save the selected glossary to in the session state
        """
        from daras_ai_v2.doc_search_settings_widgets import document_uploader

        glossary_url = document_uploader(
            label=label,
            key=key,
            accept=["csv", "xlsx", "xls", "gsheet", "ods", "tsv"],
            accept_multiple_files=False,
        )
        st.caption(
            f"If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing)."
        )
        return glossary_url


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


# ================================ Glossary ================================
# Below follows code for uploading a glossary to Google Cloud Translate.
# Using a glossary is a good approach if you don’t have enough data to train your own model
# when working with minority languages which Google still has a lot of room for improvement
# or when you are working with a domain specific topic.
PROJECT_ID = "dara-c1b52"  # GCP project id
GLOSSARY_NAME = "glossary"  # name you want to give this glossary resource
LOCATION = "us-central1"  # data center location
BUCKET_NAME = "gooey-server-glossary"  # name of bucket
BLOB_NAME = "glossary.csv"  # name of blob
GLOSSARY_URI = (
    "gs://" + BUCKET_NAME + "/" + BLOB_NAME
)  # the uri of the glossary uploaded to Cloud Storage


def _mask_glossary(
    text: str,
    source_language: LANGUAGE_CODE_TYPE,
    target_language: LANGUAGE_CODE_TYPE,
    glossary: "pd.DataFrame",
) -> tuple[str, list[str]]:
    if source_language in glossary.columns and target_language in glossary.columns:
        glossies = dict(zip(glossary[source_language], glossary[target_language]))
        replaced_glossies = []
        for source_glossary in glossies.keys():
            pattern = re.compile(re.escape(source_glossary), re.IGNORECASE)
            occurences = len(pattern.findall(text))
            text = pattern.sub("(" + EN_NUMERALS + ")", text)
            replaced_glossies += [source_glossary] * occurences
        return text, map(lambda x: glossies[x], replaced_glossies)
    return text, []


def _unmask_glossary(
    text: str, replaced_glossies: list[str], target_language: LANGUAGE_CODE_TYPE
) -> str:
    for target_glossary in replaced_glossies:
        try:
            to_replace = NATIVE_NUMERALS[LANG2SCRIPT[target_language]]
        except:
            to_replace = EN_NUMERALS
        text = text.replace(
            "(" + to_replace + ")",
            target_glossary,
            1,
        )
    return text


def _update_or_create_glossary(f_url: str) -> tuple[str, "pd.DataFrame"]:
    """
    Update or create a glossary resource
    Args:
        f_url: url of the glossary file
    Returns:
        name: path to the glossary resource
        df: pandas DataFrame of the glossary
    """
    from daras_ai_v2.vector_search import doc_url_to_metadata

    print("Updating/Creating glossary...")
    f_url = f_url or DEFAULT_GLOSSARY_URL
    doc_meta = doc_url_to_metadata(f_url)
    df = _update_glossary(f_url, doc_meta)
    return f"projects/{PROJECT_ID}/locations/{LOCATION}/glossaries/{GLOSSARY_NAME}", df


@redis_cache_decorator
def _update_glossary(f_url: str, doc_meta) -> "pd.DataFrame":
    from daras_ai_v2.vector_search import download_table_doc

    df = download_table_doc(f_url, doc_meta)

    _upload_glossary_to_bucket(df)
    # delete existing glossary
    try:
        _delete_glossary()
    except:
        pass
    # create new glossary
    languages = [
        lan_code
        for lan_code in df.columns.tolist()
        if lan_code not in ["pos", "description"]
    ]  # these are not languages
    _create_glossary(languages)

    return df


def _get_glossary():
    """Get information about a particular glossary."""
    from google.cloud import translate_v3beta1

    client = translate_v3beta1.TranslationServiceClient()

    name = client.glossary_path(PROJECT_ID, LOCATION, GLOSSARY_NAME)

    response = client.get_glossary(name=name)
    print("Glossary name: {}".format(response.name))
    print("Entry count: {}".format(response.entry_count))
    print("Input URI: {}".format(response.input_config.gcs_source.input_uri))
    return name


def _upload_glossary_to_bucket(df):
    """Uploads a pandas DataFrame to the bucket."""
    # import gcloud storage
    from google.cloud import storage

    csv = df.to_csv(index=False)

    # initialize the storage client and give it the bucket and the blob name
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(BLOB_NAME)

    # upload the file to the bucket
    blob.upload_from_string(csv)


def _delete_glossary(timeout=180):
    """Delete a specific glossary based on the glossary ID."""
    from google.cloud import translate_v3beta1

    client = translate_v3beta1.TranslationServiceClient()

    name = client.glossary_path(PROJECT_ID, LOCATION, GLOSSARY_NAME)

    operation = client.delete_glossary(name=name)
    result = operation.result(timeout)
    print("Deleted: {}".format(result.name))


def _create_glossary(languages):
    """Creates a GCP glossary resource
    Assumes you've already uploaded a glossary to Cloud Storage bucket
    Args:
        languages: list of languages in the glossary
        project_id: GCP project id
        glossary_name: name you want to give this glossary resource
        glossary_uri: the uri of the glossary you uploaded to Cloud Storage
    """
    from google.cloud import translate_v3beta1
    from google.api_core.exceptions import AlreadyExists

    # Instantiates a client
    client = translate_v3beta1.TranslationServiceClient()

    # Set glossary resource name
    name = client.glossary_path(PROJECT_ID, LOCATION, GLOSSARY_NAME)

    # Set language codes
    language_codes_set = translate_v3beta1.Glossary.LanguageCodesSet(
        language_codes=languages
    )

    gcs_source = translate_v3beta1.GcsSource(input_uri=GLOSSARY_URI)

    input_config = translate_v3beta1.GlossaryInputConfig(gcs_source=gcs_source)

    # Set glossary resource information
    glossary = translate_v3beta1.Glossary(
        name=name, language_codes_set=language_codes_set, input_config=input_config
    )

    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"

    # Create glossary resource
    # Handle exception for case in which a glossary
    #  with glossary_name already exists
    try:
        operation = client.create_glossary(parent=parent, glossary=glossary)
        operation.result(timeout=90)
        print("Created glossary " + GLOSSARY_NAME + ".")
    except AlreadyExists:
        print(
            "The glossary "
            + GLOSSARY_NAME
            + " already exists. No new glossary was created."
        )
