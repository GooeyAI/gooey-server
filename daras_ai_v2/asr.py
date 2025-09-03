from __future__ import annotations

import multiprocessing
import os.path
import tempfile
import threading
import typing
from enum import Enum
from functools import lru_cache

import gooey_gui as gui
import requests
import typing_extensions
from django.db.models import F
from furl import furl

from daras_ai.image_input import upload_file_from_bytes, gs_url_to_uri
from daras_ai_v2 import settings
from daras_ai_v2.azure_asr import azure_asr
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import (
    raise_for_status,
    UserError,
    ffmpeg,
    call_cmd,
    ffprobe,
)
from daras_ai_v2.functional import map_parallel, flatten
from daras_ai_v2.gdrive_downloader import (
    is_gdrive_url,
    gdrive_download,
    gdrive_metadata,
    url_to_gdrive_file_id,
)
from daras_ai_v2.google_asr import gcp_asr_v1
from daras_ai_v2.gpu_server import call_celery_task
from daras_ai_v2.language_filters import (
    filter_languages,
    filter_models_by_language,
    normalised_lang_in_collection,
    are_languages_same,
)
from daras_ai_v2.redis_cache import redis_cache_decorator
from daras_ai_v2.scraping_proxy import SCRAPING_PROXIES, get_scraping_proxy_cert_path
from daras_ai_v2.text_splitter import text_splitter

if typing.TYPE_CHECKING:
    import google.cloud.speech_v2
    from google.auth.transport.requests import AuthorizedSession

TRANSLATE_BATCH_SIZE = 8

SHORT_FILE_CUTOFF = 5 * 1024 * 1024  # 1 MB

# https://cloud.google.com/translate/docs/languages#roman
TRANSLITERATION_SUPPORTED = {"ar", "bn", " gu", "hi", "ja", "kn", "ru", "ta", "te"}

# https://cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages
GCP_V1_SUPPORTED = {
    "af-ZA", "sq-AL", "am-ET", "ar-DZ", "ar-BH", "ar-EG", "ar-IQ", "ar-IL", "ar-JO", "ar-KW", "ar-LB", "ar-MR", "ar-MA",
    "ar-OM", "ar-QA", "ar-SA", "ar-PS", "ar-SY", "ar-TN", "ar-AE", "ar-YE", "hy-AM", "az-AZ", "eu-ES", "bn-BD", "bn-IN",
    "bs-BA", "bg-BG", "my-MM", "ca-ES", "yue-Hant-HK", "zh", "zh-TW", "hr-HR", "cs-CZ",
    "da-DK", "nl-BE", "nl-NL", "en-AU", "en-CA", "en-GH", "en-HK", "en-IN", "en-IE", "en-KE", "en-NZ", "en-NG", "en-PK",
    "en-PH", "en-SG", "en-ZA", "en-TZ", "en-GB", "en-US", "et-EE", "fil-PH", "fi-FI", "fr-BE", "fr-CA", "fr-FR",
    "fr-CH", "gl-ES", "ka-GE", "de-AT", "de-DE", "de-CH", "el-GR", "gu-IN", "iw-IL", "hi-IN", "hu-HU", "is-IS", "id-ID",
    "it-IT", "it-CH", "ja-JP", "jv-ID", "kn-IN", "kk-KZ", "km-KH", "ko-KR", "lo-LA", "lv-LV", "lt-LT", "mk-MK", "ms-MY",
    "ml-IN", "mr-IN", "mn-MN", "ne-NP", "no-NO", "fa-IR", "pl-PL", "pt-BR", "pt-PT", "pa-Guru-IN", "ro-RO", "ru-RU",
    "sr-RS", "si-LK", "sk-SK", "sl-SI", "es-AR", "es-BO", "es-CL", "es-CO", "es-CR", "es-DO", "es-EC", "es-SV", "es-GT",
    "es-HN", "es-MX", "es-NI", "es-PA", "es-PY", "es-PE", "es-PR", "es-ES", "es-US", "es-UY", "es-VE", "su-ID", "sw-KE",
    "sw-TZ", "sv-SE", "ta-IN", "ta-MY", "ta-SG", "ta-LK", "te-IN", "th-TH", "tr-TR", "uk-UA", "ur-IN", "ur-PK", "uz-UZ",
    "vi-VN", "zu-ZA",
}  # fmt: skip

# https://cloud.google.com/speech-to-text/v2/docs/speech-to-text-supported-languages
CHIRP_SUPPORTED = {
    'fa-IR', 'sr-RS', 'es-US', 'ur-PK', 'yo-NG', 'te-IN', 'sn-ZW', 'es-ES', 'jv-ID', 'cmn-Hans-CN', 'ha-NG', 'no-NO',
    'wo-SN', 'ceb-PH', 'ms-MY', 'ny-MW', 'et-EE', 'kn-IN', 'sd-IN', 'en-GB', 'ml-IN', 'fil-PH', 'my-MM', 'uk-UA',
    'lt-LT', 'en-US', 'su-ID', 'ru-RU', 'en-IN', 'it-IT', 'ky-KG', 'en-AU', 'id-ID', 'ja-JP', 'fr-CA', 'nl-NL', 'fi-FI',
    'zu-ZA', 'ar-EG', 'bs-BA', 'gl-ES', 'si-LK', 'pa-Guru-IN', 'ast-ES', 'tr-TR', 'mt-MT', 'hy-AM', 'da-DK', 'vi-VN',
    'kam-KE', 'hu-HU', 'cs-CZ', 'sl-SI', 'ko-KR', 'km-KH', 'kk-KZ', 'nso-ZA', 'mk-MK', 'de-DE', 'mr-IN', 'th-TH',
    'as-IN', 'kea-CV', 'bg-BG', 'sk-SK', 'el-GR', 'cy-GB', 'ro-RO', 'ckb-IQ', 'ca-ES', 'sq-AL', 'af-ZA', 'cmn-Hant-TW',
    'mi-NZ', 'gu-IN', 'tg-TJ', 'oc-FR', 'so-SO', 'be-BY', 'fr-FR', 'luo-KE', 'sv-SE', 'is-IS', 'uz-UZ', 'iw-IL',
    'ps-AF', 'ta-IN', 'sw', 'mn-MN', 'ka-GE', 'az-AZ', 'pt-BR', 'hi-IN', 'lo-LA', 'am-ET', 'eu-ES', 'yue-Hant-HK',
    'pl-PL', 'hr-HR', 'lv-LV', 'ln-CD', 'ne-NP', 'lb-LU'
}  # fmt: skip

WHISPER_LARGE_V2_SUPPORTED = {
    "af", "ar", "hy", "az", "be", "bs", "bg", "ca", "zh", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "gl", "de",
    "el", "he", "hi", "hu", "is", "id", "it", "ja", "kn", "kk", "ko", "lv", "lt", "mk", "ms", "mr", "mi", "ne", "no",
    "fa", "pl", "pt", "ro", "ru", "sr", "sk", "sl", "es", "sw", "sv", "tl", "ta", "th", "tr", "uk", "ur", "vi", "cy"
}  # fmt: skip

# this map exists because replicate is stupid
WHISPER_LARGE_V3_SUPPORTED = {
    "af": "afrikaans", "sq": "albanian", "am": "amharic", "ar": "arabic", "hy": "armenian", "as": "assamese",
    "az": "azerbaijani", "ba": "bashkir", "eu": "basque", "be": "belarusian", "bn": "bengali", "bs": "bosnian",
    "br": "breton", "bg": "bulgarian", "yue": "cantonese", "ca": "catalan", "zh": "chinese", "hr": "croatian",
    "cs": "czech", "da": "danish", "nl": "dutch", "en": "english", "et": "estonian", "fo": "faroese", "fi": "finnish",
    "fr": "french", "gl": "galician", "ka": "georgian", "de": "german", "el": "greek", "gu": "gujarati",
    "ht": "haitian creole", "ha": "hausa", "haw": "hawaiian", "he": "hebrew", "hi": "hindi", "hu": "hungarian",
    "is": "icelandic", "id": "indonesian", "it": "italian", "ja": "japanese", "jv": "javanese", "kn": "kannada",
    "kk": "kazakh", "km": "khmer", "ko": "korean", "lo": "lao", "la": "latin", "lv": "latvian", "ln": "lingala",
    "lt": "lithuanian", "lb": "luxembourgish", "mk": "macedonian", "mg": "malagasy", "ms": "malay", "ml": "malayalam",
    "mt": "maltese", "mi": "maori", "mr": "marathi", "mn": "mongolian", "my": "myanmar", "ne": "nepali",
    "no": "norwegian", "nn": "nynorsk", "oc": "occitan", "ps": "pashto", "fa": "persian", "pl": "polish",
    "pt": "portuguese", "pa": "punjabi", "ro": "romanian", "ru": "russian", "sa": "sanskrit", "sr": "serbian",
    "sn": "shona", "sd": "sindhi", "si": "sinhala", "sk": "slovak", "sl": "slovenian", "so": "somali", "es": "spanish",
    "su": "sundanese", "sw": "swahili", "sv": "swedish", "tl": "tagalog", "tg": "tajik", "ta": "tamil", "tt": "tatar",
    "te": "telugu", "th": "thai", "bo": "tibetan", "tr": "turkish", "tk": "turkmen", "uk": "ukrainian", "ur": "urdu",
    "uz": "uzbek", "vi": "vietnamese", "cy": "welsh", "yi": "yiddish", "yo": "yoruba",
}  # fmt: skip

# https://huggingface.co/facebook/seamless-m4t-v2-large#supported-languages
# For now, below are listed the languages that support ASR. Note that Seamless only accepts ISO 639-3 codes.
SEAMLESS_v2_ASR_SUPPORTED = {
    "afr", "amh", "arb", "ary", "arz", "asm", "azj", "bel", "ben", "bos", "bul", "cat", "ceb", "ces", "ckb", "cmn",
    "cmn-Hant", "cym", "dan", "deu", "ell", "eng", "est", "eus", "fin", "fra", "fuv", "gaz", "gle", "glg", "guj", "heb",
    "hin", "hrv", "hun", "hye", "ibo", "ind", "isl", "ita", "jav", "jpn", "kan", "kat", "kaz", "khk", "khm", "kir",
    "kor", "lao", "lit", "lug", "luo", "lvs", "mai", "mal", "mar", "mkd", "mlt", "mni", "mya", "nld", "nno", "nob",
    "npi", "nya", "ory", "pan", "pbt", "pes", "pol", "por", "ron", "rus", "slk", "slv", "sna", "snd", "som", "spa",
    "srp", "swe", "swh", "tam", "tel", "tgk", "tgl", "tha", "tur", "ukr", "urd", "uzn", "vie", "yor", "yue", "zul",
}  # fmt: skip

# Eleven Labs Scribe v1 - supports 99 languages with 3-letter ISO codes
ELEVENLABS_SUPPORTED = {
    "afr", "amh", "ara", "hye", "asm", "ast", "aze", "bel", "ben", "bos", "bul", "mya", "yue", "cat", "ceb", "nya",
    "hrv", "ces", "dan", "nld", "eng", "est", "fil", "fin", "fra", "ful", "glg", "lug", "kat", "deu", "ell", "guj",
    "hau", "heb", "hin", "hun", "isl", "ibo", "ind", "gle", "ita", "jpn", "jav", "kea", "kan", "kaz", "khm", "kor",
    "kur", "kir", "lao", "lav", "lin", "lit", "luo", "ltz", "mkd", "msa", "mal", "mlt", "zho", "mri", "mar", "mon",
    "nep", "nso", "nor", "oci", "ori", "pus", "fas", "pol", "por", "pan", "ron", "rus", "srp", "sna", "snd", "slk",
    "slv", "som", "spa", "swa", "swe", "tam", "tgk", "tel", "tha", "tur", "ukr", "umb", "urd", "uzb", "vie", "cym",
    "wol", "xho", "zul",
}  # fmt: skip

AZURE_SUPPORTED = {
    "af-ZA", "am-ET", "ar-AE", "ar-BH", "ar-DZ", "ar-EG", "ar-IL", "ar-IQ", "ar-JO", "ar-KW", "ar-LB", "ar-LY", "ar-MA",
    "ar-OM", "ar-PS", "ar-QA", "ar-SA", "ar-SY", "ar-TN", "ar-YE", "az-AZ", "bg-BG", "bn-IN", "bs-BA", "ca-ES", "cs-CZ",
    "cy-GB", "da-DK", "de-AT", "de-CH", "de-DE", "el-GR", "en-AU", "en-CA", "en-GB", "en-GH", "en-HK", "en-IE", "en-IN",
    "en-KE", "en-NG", "en-NZ", "en-PH", "en-SG", "en-TZ", "en-US", "en-ZA", "es-AR", "es-BO", "es-CL", "es-CO", "es-CR",
    "es-CU", "es-DO", "es-EC", "es-ES", "es-GQ", "es-GT", "es-HN", "es-MX", "es-NI", "es-PA", "es-PE", "es-PR", "es-PY",
    "es-SV", "es-US", "es-UY", "es-VE", "et-EE", "eu-ES", "fa-IR", "fi-FI", "fil-PH", "fr-BE", "fr-CA", "fr-CH",
    "fr-FR", "ga-IE", "gl-ES", "gu-IN", "he-IL", "hi-IN", "hr-HR", "hu-HU", "hy-AM", "id-ID", "is-IS", "it-CH", "it-IT",
    "ja-JP", "jv-ID", "ka-GE", "kk-KZ", "km-KH", "kn-IN", "ko-KR", "lo-LA", "lt-LT", "lv-LV", "mk-MK", "ml-IN", "mn-MN",
    "mr-IN", "ms-MY", "mt-MT", "my-MM", "nb-NO", "ne-NP", "nl-BE", "nl-NL", "pa-IN", "pl-PL", "ps-AF", "pt-BR", "pt-PT",
    "ro-RO", "ru-RU", "si-LK", "sk-SK", "sl-SI", "so-SO", "sq-AL", "sr-RS", "sv-SE", "sw-KE", "sw-TZ", "ta-IN", "te-IN",
    "th-TH", "tr-TR", "uk-UA", "ur-IN", "uz-UZ", "vi-VN", "wuu-CN", "yue-CN", "zh-CN", "zh-CN-shandong",
    "zh-CN-sichuan", "zh-HK", "zh-TW", "zu-ZA"
}  # fmt: skip

# https://deepgram.com/product/languages for the "general" model:
# DEEPGRAM_SUPPORTED = {"nl","en","en-AU","en-US","en-GB","en-NZ","en-IN","fr","fr-CA","de","hi","hi-Latn","id","it","ja","ko","cmn-Hans-CN","cmn-Hant-TW","no","pl","pt","pt-PT","pt-BR","ru","es","es-419","sv","tr","uk"}  # fmt: skip
# but we only have the Nova tier so these are our languages (https://developers.deepgram.com/docs/models-languages-overview):
DEEPGRAM_SUPPORTED = {"en", "en-US", "en-AU", "en-GB", "en-NZ", "en-IN", "es", "es-419"}  # fmt: skip

# https://huggingface.co/spaces/mms-meta/MMS/raw/main/data/asr/all_langs.tsv
MMS_SUPPORTED = {
    'abi', 'abk', 'abp', 'aca', 'acd', 'ace', 'acf', 'ach', 'acn', 'acr', 'acu', 'ade', 'adh', 'adj', 'adx', 'aeu',
    'afr', 'agd', 'agg', 'agn', 'agr', 'agu', 'agx', 'aha', 'ahk', 'aia', 'aka', 'akb', 'ake', 'akp', 'alj', 'alp',
    'alt', 'alz', 'ame', 'amf', 'amh', 'ami', 'amk', 'ann', 'any', 'aoz', 'apb', 'apr', 'ara', 'arl', 'asa', 'asg',
    'asm', 'ast', 'ata', 'atb', 'atg', 'ati', 'atq', 'ava', 'avn', 'avu', 'awa', 'awb', 'ayo', 'ayr', 'ayz', 'azb',
    'azg', 'azj-script_cyrillic', 'azj-script_latin', 'azz', 'bak', 'bam', 'ban', 'bao', 'bas', 'bav', 'bba', 'bbb',
    'bbc', 'bbo', 'bcc-script_arabic', 'bcc-script_latin', 'bcl', 'bcw', 'bdg', 'bdh', 'bdq', 'bdu', 'bdv', 'beh',
    'bel', 'bem', 'ben', 'bep', 'bex', 'bfa', 'bfo', 'bfy', 'bfz', 'bgc', 'bgq', 'bgr', 'bgt', 'bgw', 'bha', 'bht',
    'bhz', 'bib', 'bim', 'bis', 'biv', 'bjr', 'bjv', 'bjw', 'bjz', 'bkd', 'bkv', 'blh', 'blt', 'blx', 'blz', 'bmq',
    'bmr', 'bmu', 'bmv', 'bng', 'bno', 'bnp', 'boa', 'bod', 'boj', 'bom', 'bor', 'bos', 'bov', 'box', 'bpr', 'bps',
    'bqc', 'bqi', 'bqj', 'bqp', 'bre', 'bru', 'bsc', 'bsq', 'bss', 'btd', 'bts', 'btt', 'btx', 'bud', 'bul', 'bus',
    'bvc', 'bvz', 'bwq', 'bwu', 'byr', 'bzh', 'bzi', 'bzj', 'caa', 'cab', 'cac-dialect_sanmateoixtatan',
    'cac-dialect_sansebastiancoatan', 'cak-dialect_central', 'cak-dialect_santamariadejesus',
    'cak-dialect_santodomingoxenacoj', 'cak-dialect_southcentral', 'cak-dialect_western', 'cak-dialect_yepocapa', 'cap',
    'car', 'cas', 'cat', 'cax', 'cbc', 'cbi', 'cbr', 'cbs', 'cbt', 'cbu', 'cbv', 'cce', 'cco', 'cdj', 'ceb', 'ceg',
    'cek', 'ces', 'cfm', 'cgc', 'che', 'chf', 'chv', 'chz', 'cjo', 'cjp', 'cjs', 'ckb', 'cko', 'ckt', 'cla', 'cle',
    'cly', 'cme', 'cmn-script_simplified', 'cmo-script_khmer', 'cmo-script_latin', 'cmr', 'cnh', 'cni', 'cnl', 'cnt',
    'coe', 'cof', 'cok', 'con', 'cot', 'cou', 'cpa', 'cpb', 'cpu', 'crh', 'crk-script_latin', 'crk-script_syllabics',
    'crn', 'crq', 'crs', 'crt', 'csk', 'cso', 'ctd', 'ctg', 'cto', 'ctu', 'cuc', 'cui', 'cuk', 'cul', 'cwa', 'cwe',
    'cwt', 'cya', 'cym', 'daa', 'dah', 'dan', 'dar', 'dbj', 'dbq', 'ddn', 'ded', 'des', 'deu', 'dga', 'dgi', 'dgk',
    'dgo', 'dgr', 'dhi', 'did', 'dig', 'dik', 'dip', 'div', 'djk', 'dnj-dialect_blowowest', 'dnj-dialect_gweetaawueast',
    'dnt', 'dnw', 'dop', 'dos', 'dsh', 'dso', 'dtp', 'dts', 'dug', 'dwr', 'dyi', 'dyo', 'dyu', 'dzo', 'eip', 'eka',
    'ell', 'emp', 'enb', 'eng', 'enx', 'epo', 'ese', 'ess', 'est', 'eus', 'evn', 'ewe', 'eza', 'fal', 'fao', 'far',
    'fas', 'fij', 'fin', 'flr', 'fmu', 'fon', 'fra', 'frd', 'fry', 'ful', 'gag-script_cyrillic', 'gag-script_latin',
    'gai', 'gam', 'gau', 'gbi', 'gbk', 'gbm', 'gbo', 'gde', 'geb', 'gej', 'gil', 'gjn', 'gkn', 'gld', 'gle', 'glg',
    'glk', 'gmv', 'gna', 'gnd', 'gng', 'gof-script_latin', 'gog', 'gor', 'gqr', 'grc', 'gri', 'grn', 'grt', 'gso',
    'gub', 'guc', 'gud', 'guh', 'guj', 'guk', 'gum', 'guo', 'guq', 'guu', 'gux', 'gvc', 'gvl', 'gwi', 'gwr', 'gym',
    'gyr', 'had', 'hag', 'hak', 'hap', 'hat', 'hau', 'hay', 'heb', 'heh', 'hif', 'hig', 'hil', 'hin', 'hlb', 'hlt',
    'hne', 'hnn', 'hns', 'hoc', 'hoy', 'hrv', 'hsb', 'hto', 'hub', 'hui', 'hun', 'hus-dialect_centralveracruz',
    'hus-dialect_westernpotosino', 'huu', 'huv', 'hvn', 'hwc', 'hye', 'hyw', 'iba', 'ibo', 'icr', 'idd', 'ifa', 'ifb',
    'ife', 'ifk', 'ifu', 'ify', 'ign', 'ikk', 'ilb', 'ilo', 'imo', 'ina', 'inb', 'ind', 'iou', 'ipi', 'iqw', 'iri',
    'irk', 'isl', 'ita', 'itl', 'itv', 'ixl-dialect_sangasparchajul', 'ixl-dialect_sanjuancotzal',
    'ixl-dialect_santamarianebaj', 'izr', 'izz', 'jac', 'jam', 'jav', 'jbu', 'jen', 'jic', 'jiv', 'jmc', 'jmd', 'jpn',
    'jun', 'juy', 'jvn', 'kaa', 'kab', 'kac', 'kak', 'kam', 'kan', 'kao', 'kaq', 'kat', 'kay', 'kaz', 'kbo', 'kbp',
    'kbq', 'kbr', 'kby', 'kca', 'kcg', 'kdc', 'kde', 'kdh', 'kdi', 'kdj', 'kdl', 'kdn', 'kdt', 'kea', 'kek', 'ken',
    'keo', 'ker', 'key', 'kez', 'kfb', 'kff-script_telugu', 'kfw', 'kfx', 'khg', 'khm', 'khq', 'kia', 'kij', 'kik',
    'kin', 'kir', 'kjb', 'kje', 'kjg', 'kjh', 'kki', 'kkj', 'kle', 'klu', 'klv', 'klw', 'kma', 'kmd', 'kml',
    'kmr-script_arabic', 'kmr-script_cyrillic', 'kmr-script_latin', 'kmu', 'knb', 'kne', 'knf', 'knj', 'knk', 'kno',
    'kog', 'kor', 'kpq', 'kps', 'kpv', 'kpy', 'kpz', 'kqe', 'kqp', 'kqr', 'kqy', 'krc', 'kri', 'krj', 'krl', 'krr',
    'krs', 'kru', 'ksb', 'ksr', 'kss', 'ktb', 'ktj', 'kub', 'kue', 'kum', 'kus', 'kvn', 'kvw', 'kwd', 'kwf', 'kwi',
    'kxc', 'kxf', 'kxm', 'kxv', 'kyb', 'kyc', 'kyf', 'kyg', 'kyo', 'kyq', 'kyu', 'kyz', 'kzf', 'lac', 'laj', 'lam',
    'lao', 'las', 'lat', 'lav', 'law', 'lbj', 'lbw', 'lcp', 'lee', 'lef', 'lem', 'lew', 'lex', 'lgg', 'lgl', 'lhu',
    'lia', 'lid', 'lif', 'lin', 'lip', 'lis', 'lit', 'lje', 'ljp', 'llg', 'lln', 'lme', 'lnd', 'lns', 'lob', 'lok',
    'lom', 'lon', 'loq', 'lsi', 'lsm', 'ltz', 'luc', 'lug', 'luo', 'lwo', 'lww', 'lzz', 'maa-dialect_sanantonio',
    'maa-dialect_sanjeronimo', 'mad', 'mag', 'mah', 'mai', 'maj', 'mak', 'mal', 'mam-dialect_central',
    'mam-dialect_northern', 'mam-dialect_southern', 'mam-dialect_western', 'maq', 'mar', 'maw', 'maz', 'mbb', 'mbc',
    'mbh', 'mbj', 'mbt', 'mbu', 'mbz', 'mca', 'mcb', 'mcd', 'mco', 'mcp', 'mcq', 'mcu', 'mda', 'mdf', 'mdv', 'mdy',
    'med', 'mee', 'mej', 'men', 'meq', 'met', 'mev', 'mfe', 'mfh', 'mfi', 'mfk', 'mfq', 'mfy', 'mfz', 'mgd', 'mge',
    'mgh', 'mgo', 'mhi', 'mhr', 'mhu', 'mhx', 'mhy', 'mib', 'mie', 'mif', 'mih', 'mil', 'mim', 'min', 'mio', 'mip',
    'miq', 'mit', 'miy', 'miz', 'mjl', 'mjv', 'mkd', 'mkl', 'mkn', 'mlg', 'mlt', 'mmg', 'mnb', 'mnf', 'mnk', 'mnw',
    'mnx', 'moa', 'mog', 'mon', 'mop', 'mor', 'mos', 'mox', 'moz', 'mpg', 'mpm', 'mpp', 'mpx', 'mqb', 'mqf', 'mqj',
    'mqn', 'mri', 'mrw', 'msy', 'mtd', 'mtj', 'mto', 'muh', 'mup', 'mur', 'muv', 'muy', 'mvp', 'mwq', 'mwv', 'mxb',
    'mxq', 'mxt', 'mxv', 'mya', 'myb', 'myk', 'myl', 'myv', 'myx', 'myy', 'mza', 'mzi', 'mzj', 'mzk', 'mzm', 'mzw',
    'nab', 'nag', 'nan', 'nas', 'naw', 'nca', 'nch', 'ncj', 'ncl', 'ncu', 'ndj', 'ndp', 'ndv', 'ndy', 'ndz', 'neb',
    'new', 'nfa', 'nfr', 'nga', 'ngl', 'ngp', 'ngu', 'nhe', 'nhi', 'nhu', 'nhw', 'nhx', 'nhy', 'nia', 'nij', 'nim',
    'nin', 'nko', 'nlc', 'nld', 'nlg', 'nlk', 'nmz', 'nnb', 'nno', 'nnq', 'nnw', 'noa', 'nob', 'nod', 'nog', 'not',
    'npi', 'npl', 'npy', 'nso', 'nst', 'nsu', 'ntm', 'ntr', 'nuj', 'nus', 'nuz', 'nwb', 'nxq', 'nya', 'nyf', 'nyn',
    'nyo', 'nyy', 'nzi', 'obo', 'oci', 'ojb-script_latin', 'ojb-script_syllabics', 'oku', 'old', 'omw', 'onb', 'ood',
    'orm', 'ory', 'oss', 'ote', 'otq', 'ozm', 'pab', 'pad', 'pag', 'pam', 'pan', 'pao', 'pap', 'pau', 'pbb', 'pbc',
    'pbi', 'pce', 'pcm', 'peg', 'pez', 'pib', 'pil', 'pir', 'pis', 'pjt', 'pkb', 'pls', 'plw', 'pmf', 'pny',
    'poh-dialect_eastern', 'poh-dialect_western', 'poi', 'pol', 'por', 'poy', 'ppk', 'pps', 'prf', 'prk', 'prt', 'pse',
    'pss', 'ptu', 'pui', 'pus', 'pwg', 'pww', 'pxm', 'qub', 'quc-dialect_central', 'quc-dialect_east',
    'quc-dialect_north', 'quf', 'quh', 'qul', 'quw', 'quy', 'quz', 'qvc', 'qve', 'qvh', 'qvm', 'qvn', 'qvo', 'qvs',
    'qvw', 'qvz', 'qwh', 'qxh', 'qxl', 'qxn', 'qxo', 'qxr', 'rah', 'rai', 'rap', 'rav', 'raw', 'rej', 'rel', 'rgu',
    'rhg', 'rif-script_arabic', 'rif-script_latin', 'ril', 'rim', 'rjs', 'rkt', 'rmc-script_cyrillic',
    'rmc-script_latin', 'rmo', 'rmy-script_cyrillic', 'rmy-script_latin', 'rng', 'rnl', 'roh-dialect_sursilv',
    'roh-dialect_vallader', 'rol', 'ron', 'rop', 'rro', 'rub', 'ruf', 'rug', 'run', 'rus', 'sab', 'sag', 'sah', 'saj',
    'saq', 'sas', 'sat', 'sba', 'sbd', 'sbl', 'sbp', 'sch', 'sck', 'sda', 'sea', 'seh', 'ses', 'sey', 'sgb', 'sgj',
    'sgw', 'shi', 'shk', 'shn', 'sho', 'shp', 'sid', 'sig', 'sil', 'sja', 'sjm', 'sld', 'slk', 'slu', 'slv', 'sml',
    'smo', 'sna', 'snd', 'sne', 'snn', 'snp', 'snw', 'som', 'soy', 'spa', 'spp', 'spy', 'sqi', 'sri', 'srm', 'srn',
    'srp-script_cyrillic', 'srp-script_latin', 'srx', 'stn', 'stp', 'suc', 'suk', 'sun', 'sur', 'sus', 'suv', 'suz',
    'swe', 'swh', 'sxb', 'sxn', 'sya', 'syl', 'sza', 'tac', 'taj', 'tam', 'tao', 'tap', 'taq', 'tat', 'tav', 'tbc',
    'tbg', 'tbk', 'tbl', 'tby', 'tbz', 'tca', 'tcc', 'tcs', 'tcz', 'tdj', 'ted', 'tee', 'tel', 'tem', 'teo', 'ter',
    'tes', 'tew', 'tex', 'tfr', 'tgj', 'tgk', 'tgl', 'tgo', 'tgp', 'tha', 'thk', 'thl', 'tih', 'tik', 'tir', 'tkr',
    'tlb', 'tlj', 'tly', 'tmc', 'tmf', 'tna', 'tng', 'tnk', 'tnn', 'tnp', 'tnr', 'tnt', 'tob', 'toc', 'toh', 'tom',
    'tos', 'tpi', 'tpm', 'tpp', 'tpt', 'trc', 'tri', 'trn', 'trs', 'tso', 'tsz', 'ttc', 'tte', 'ttq-script_tifinagh',
    'tue', 'tuf', 'tuk-script_arabic', 'tuk-script_latin', 'tuo', 'tur', 'tvw', 'twb', 'twe', 'twu', 'txa', 'txq',
    'txu', 'tye', 'tzh-dialect_bachajon', 'tzh-dialect_tenejapa', 'tzj-dialect_eastern', 'tzj-dialect_western',
    'tzo-dialect_chamula', 'tzo-dialect_chenalho', 'ubl', 'ubu', 'udm', 'udu', 'uig-script_arabic',
    'uig-script_cyrillic', 'ukr', 'umb', 'unr', 'upv', 'ura', 'urb', 'urd-script_arabic', 'urd-script_devanagari',
    'urd-script_latin', 'urk', 'urt', 'ury', 'usp', 'uzb-script_cyrillic', 'uzb-script_latin', 'vag', 'vid', 'vie',
    'vif', 'vmw', 'vmy', 'vot', 'vun', 'vut', 'wal-script_ethiopic', 'wal-script_latin', 'wap', 'war', 'waw', 'way',
    'wba', 'wlo', 'wlx', 'wmw', 'wob', 'wol', 'wsg', 'wwa', 'xal', 'xdy', 'xed', 'xer', 'xho', 'xmm', 'xnj', 'xnr',
    'xog', 'xon', 'xrb', 'xsb', 'xsm', 'xsr', 'xsu', 'xta', 'xtd', 'xte', 'xtm', 'xtn', 'xua', 'xuo', 'yaa', 'yad',
    'yal', 'yam', 'yao', 'yas', 'yat', 'yaz', 'yba', 'ybb', 'ycl', 'ycn', 'yea', 'yka', 'yli', 'yor', 'yre', 'yua',
    'yue-script_traditional', 'yuz', 'yva', 'zaa', 'zab', 'zac', 'zad', 'zae', 'zai', 'zam', 'zao', 'zaq', 'zar', 'zas',
    'zav', 'zaw', 'zca', 'zga', 'zim', 'ziw', 'zlm', 'zmz', 'zne', 'zos', 'zpc', 'zpg', 'zpi', 'zpl', 'zpm', 'zpo',
    'zpt', 'zpu', 'zpz', 'ztq', 'zty', 'zul', 'zyb', 'zyp', 'zza'
}  # fmt: skip

SUNBIRD_SUPPORTED_LANGUAGES = {
    "ach": "<|su|>", "eng": "<|en|>", "kin": "<|as|>", "lgg": "<|jw|>", "lug": "<|ba|>", "myx": "<|mg|>",
    "nyn": "<|ha|>", "swa": "<|sw|>", "teo": "<|ln|>", "ttj": "<|tt|>", "xog": "<|haw|>"
}  # fmt: skip


# https://translation.ghananlp.org/api-details#api=ghananlp-translation-webservice-api
GHANA_NLP_SUPPORTED = {'en': 'English', 'tw': 'Twi', 'gaa': 'Ga', 'ee': 'Ewe', 'fat': 'Fante', 'dag': 'Dagbani',
                       'gur': 'Gurene', 'yo': 'Yoruba', 'ki': 'Kikuyu', 'luo': 'Luo', 'mer': 'Kimeru'}  # fmt: skip
GHANA_NLP_MAXLEN = 500
GHANA_API_AUTH_HEADERS = {"Ocp-Apim-Subscription-Key": str(settings.GHANA_NLP_SUBKEY)}
GHANA_NLP_ASR_V2_SUPPORTED = {
    "tw": "Twi",
    "gaa": "Ga",
    "dag": "Dagbani",
    "yo": "Yoruba",
    "ee": "Ewe",
    "ki": "Kikuyu",
}

# https://docs.lelapa.ai/getting-started/language-support
LELAPA_ASR_SUPPORTED = {"eng", "afr", "zul", "sot", "fra"}
LELAPA_MT_SUPPORTED = {"nso_Latn", "afr_Latn", "sot_Latn", "ssw_Latn", "tso_Latn", "tsn_Latn", "xho_Latn", "zul_Latn", "eng_Latn", "swh_Latn", "sna_Latn", "yor_Latn", "hau_Latn"}  # fmt: skip

# Meta Omnilingual ASR - supports 1600+ languages in flores200 format (e.g., "eng_Latn")
# https://github.com/facebookresearch/omnilingual-asr/blob/main/src/omnilingual_asr/models/wav2vec2_llama/lang_ids.py
OMNILINGUAL_ASR_SUPPORTED = {
    "aae_Latn", "aal_Latn", "abb_Latn", "abi_Latn", "abk_Cyrl", "abn_Latn", "abp_Latn", "abr_Latn", "abs_Latn", "aca_Latn", "acd_Latn", "ace_Latn", "acf_Latn", "ach_Latn", "acm_Arab", "acn_Latn", "acr_Latn", "acu_Latn", "acw_Arab", "ade_Latn", "adh_Latn", "adj_Latn", "adx_Tibt", "ady_Cyrl", "aeb_Arab", "aec_Arab", "aeu_Latn", "afb_Arab", "afo_Latn", "afr_Latn", "agd_Latn", "agg_Latn", "agn_Latn", "agr_Latn", "agu_Latn", "agx_Cyrl", "aha_Latn", "ahk_Latn", "ahl_Latn", "ahs_Latn", "aia_Latn", "ajg_Latn", "aka_Latn", "akb_Latn", "ake_Latn", "akp_Latn", "ala_Latn", "alj_Latn", "aln_Latn", "alo_Latn", "alp_Latn", "als_Latn", "alt_Cyrl", "alz_Latn", "ame_Latn", "amf_Latn", "amh_Ethi", "ami_Latn", "amk_Latn", "amu_Latn", "anc_Latn", "ank_Latn", "ann_Latn", "anp_Deva", "anw_Latn", "any_Latn", "aom_Latn", "aoz_Latn", "apb_Latn", "apc_Arab", "apd_Arab", "apr_Latn", "arb_Arab", "arg_Latn", "arl_Latn", "arq_Arab", "ars_Arab", "ary_Arab", "arz_Arab", "asa_Latn", "asg_Latn", "asm_Beng", "ast_Latn", "ata_Latn", "atb_Latn", "atg_Latn", "ati_Latn", "atq_Latn", "ava_Cyrl", "avn_Latn", "avu_Latn", "awa_Deva", "awb_Latn", "awo_Latn", "ayl_Arab", "ayo_Latn", "ayp_Arab", "ayr_Latn", "ayz_Latn", "aze_Arab", "aze_Cyrl", "aze_Latn", "azg_Latn", "azz_Latn", "bag_Latn", "bak_Cyrl", "bam_Latn", "ban_Latn", "bao_Latn", "bas_Latn", "bav_Latn", "bax_Latn", "bba_Latn", "bbb_Latn", "bbc_Latn", "bbj_Latn", "bbl_Geor", "bbo_Latn", "bbu_Latn", "bcc_Arab", "bcc_Latn", "bce_Latn", "bci_Latn", "bcl_Latn", "bcs_Latn", "bcw_Latn", "bcy_Latn", "bcz_Latn", "bda_Latn", "bde_Latn", "bdg_Latn", "bdh_Latn", "bdm_Latn", "bdq_Latn", "bdu_Latn", "beb_Latn", "beh_Latn", "bel_Cyrl", "bem_Latn", "ben_Beng", "bep_Latn", "bew_Latn", "bex_Latn", "bfa_Latn", "bfd_Latn", "bfo_Latn", "bft_Arab", "bfy_Deva", "bfz_Deva", "bgc_Deva", "bgp_Arab", "bgq_Deva", "bgr_Latn", "bgt_Latn", "bgw_Deva", "bha_Deva", "bhb_Deva", "bhh_Cyrl", "bho_Deva", "bhp_Latn", "bht_Deva", "bhz_Latn", "bib_Latn", "bim_Latn", "bis_Latn", "biv_Latn", "bjj_Deva", "bjk_Latn", "bjn_Latn", "bjr_Latn", "bjt_Latn", "bjv_Latn", "bjw_Latn", "bjz_Latn", "bkd_Latn", "bkh_Latn", "bkm_Latn", "bkv_Latn", "bky_Latn", "ble_Latn", "blh_Latn", "blt_Latn", "blx_Latn", "blz_Latn", "bmm_Latn", "bmq_Latn", "bmr_Latn", "bmu_Latn", "bmv_Latn", "bng_Beng", "bnm_Latn", "bnn_Latn", "bno_Latn", "bnp_Latn", "bns_Deva", "boa_Latn", "bod_Tibt", "boj_Latn", "bom_Latn", "bor_Latn", "bos_Latn", "bou_Latn", "bov_Latn", "box_Latn", "bpr_Latn", "bps_Latn", "bqc_Latn", "bqg_Latn", "bqi_Arab", "bqj_Latn", "bqp_Latn", "bra_Deva", "bre_Latn", "brh_Arab", "bri_Latn", "bru_Latn", "brx_Deva", "bsc_Latn", "bsh_Arab", "bsj_Latn", "bsk_Latn", "bsq_Latn", "bss_Latn", "bsy_Latn", "btd_Latn", "btm_Latn", "bts_Latn", "btt_Latn", "btv_Arab", "btx_Latn", "bud_Latn", "bug_Latn", "bul_Cyrl", "bum_Latn", "buo_Latn", "bus_Latn", "bux_Latn", "bvb_Latn", "bvc_Latn", "bvz_Latn", "bwq_Latn", "bwr_Latn", "bwu_Latn", "bxf_Latn", "bxk_Latn", "byc_Latn", "byr_Latn", "bys_Latn", "byv_Latn", "byx_Latn", "bzh_Latn", "bzi_Thai", "bzj_Latn", "bzw_Latn", "caa_Latn", "cab_Latn", "cac_Latn", "cak_Latn", "cap_Latn", "car_Latn", "cas_Latn", "cat_Latn", "cax_Latn", "cbc_Latn", "cbi_Latn", "cbr_Latn", "cbs_Latn", "cbt_Latn", "cbu_Latn", "cbv_Latn", "cce_Latn", "ccg_Latn", "cco_Latn", "cdj_Deva", "cdo_Hans", "ceb_Latn", "ceg_Latn", "cek_Latn", "cen_Latn", "ces_Latn", "cfa_Latn", "cfm_Latn", "cgc_Latn", "cgg_Latn", "che_Cyrl", "chf_Latn", "chq_Latn", "chv_Cyrl", "chz_Latn", "cjk_Latn", "cjo_Latn", "cjp_Latn", "cjs_Cyrl", "ckb_Arab", "ckl_Latn", "cko_Latn", "ckr_Latn", "ckt_Cyrl", "cky_Latn", "cla_Latn", "cle_Latn", "cly_Latn", "cme_Latn", "cmn_Hans", "cmn_Hant", "cmo_Khmr", "cmo_Latn", "cmr_Latn", "cnh_Latn", "cni_Latn", "cnl_Latn", "cnt_Latn", "coe_Latn", "cof_Latn", "cok_Latn", "con_Latn", "cor_Latn", "cot_Latn", "cou_Latn", "cpa_Latn", "cpb_Latn", "cpu_Latn", "cpx_Hans", "cpy_Latn", "crh_Cyrl", "crk_Cans", "crk_Latn", "crn_Latn", "crq_Latn", "crs_Latn", "crt_Latn", "csk_Latn", "cso_Latn", "ctd_Latn", "cte_Latn", "ctg_Beng", "ctl_Latn", "cto_Latn", "ctu_Latn", "cuc_Latn", "cui_Latn", "cuk_Latn", "cul_Latn", "cut_Latn", "cux_Latn", "cwa_Latn", "cwe_Latn", "cwt_Latn", "cya_Latn", "cym_Latn", "daa_Latn", "dag_Latn", "dah_Latn", "dan_Latn", "dar_Cyrl", "dav_Latn", "dbd_Latn", "dbj_Latn", "dbq_Latn", "dcc_Arab", "ddn_Latn", "ded_Latn", "deg_Latn", "des_Latn", "deu_Latn", "dga_Latn", "dgh_Latn", "dgi_Latn", "dgk_Latn", "dgo_Deva", "dgr_Latn", "dhi_Deva", "did_Latn", "dig_Latn", "dik_Latn", "dip_Latn", "div_Thaa", "dje_Latn", "djk_Latn", "dmk_Arab", "dml_Arab", "dnj_Latn", "dnt_Latn", "dnw_Latn", "dop_Latn", "dos_Latn", "dru_Latn", "dsb_Latn", "dsh_Latn", "dtp_Latn", "dts_Latn", "dty_Deva", "dua_Latn", "dug_Latn", "dwr_Latn", "dyi_Latn", "dyo_Latn", "dyu_Latn", "dzg_Latn", "dzo_Tibt", "ebu_Latn", "ego_Latn", "eip_Latn", "eiv_Latn", "eka_Latn", "ekk_Latn", "eko_Latn", "ekr_Latn", "ell_Grek", "ell_Grek_cypr1249", "elm_Latn", "emp_Latn", "enb_Latn", "eng_Latn", "enx_Latn", "epo_Latn", "ese_Latn", "ess_Latn", "esu_Latn", "eto_Latn", "ets_Latn", "etu_Latn", "eus_Latn", "evn_Cyrl", "ewe_Latn", "ewo_Latn", "eyo_Latn", "eza_Latn", "fal_Latn", "fan_Latn", "fao_Latn", "far_Latn", "fas_Arab", "fat_Latn", "fia_Latn", "fij_Latn", "fil_Latn", "fin_Latn", "fip_Latn", "fkk_Latn", "flr_Latn", "fmp_Latn", "fmu_Deva", "fon_Latn", "fra_Latn", "frd_Latn", "fry_Latn", "fub_Latn", "fuc_Latn", "fue_Latn", "ful_Latn", "fuq_Latn", "fuv_Latn", "gag_Cyrl", "gag_Latn", "gai_Latn", "gam_Latn", "gau_Telu", "gbi_Latn", "gbk_Deva", "gbm_Deva", "gbo_Latn", "gbr_Latn", "gby_Latn", "gcc_Latn", "gde_Latn", "gdf_Latn", "geb_Latn", "gej_Latn", "ges_Latn", "ggg_Arab", "gid_Latn", "gig_Arab", "gil_Latn", "giz_Latn", "gjk_Arab", "gjn_Latn", "gju_Arab", "gkn_Latn", "gld_Cyrl", "gle_Latn", "glg_Latn", "glk_Arab", "glv_Latn", "glw_Latn", "gmv_Latn", "gna_Latn", "gnd_Latn", "gng_Latn", "gof_Latn", "gog_Latn", "gol_Latn", "gom_Deva", "gor_Latn", "gqr_Latn", "grc_Grek", "gri_Latn", "grn_Latn", "grt_Beng", "gsl_Latn", "gso_Latn", "gub_Latn", "guc_Latn", "gud_Latn", "gug_Latn", "guh_Latn", "gui_Latn", "guj_Gujr", "guk_Ethi", "gum_Latn", "guo_Latn", "guq_Latn", "gur_Latn", "guu_Latn", "gux_Latn", "guz_Latn", "gvc_Latn", "gvl_Latn", "gwc_Arab", "gwe_Latn", "gwi_Latn", "gwr_Latn", "gwt_Arab", "gym_Latn", "gyr_Latn", "gyz_Latn", "had_Latn", "hag_Latn", "hah_Latn", "hak_Latn", "hao_Latn", "hap_Latn", "hat_Latn", "hau_Latn", "haw_Latn", "hay_Latn", "hbb_Latn", "hch_Latn", "heb_Hebr", "heh_Latn", "her_Latn", "hia_Latn", "hif_Latn", "hig_Latn", "hil_Latn", "hin_Deva", "hkk_Latn", "hla_Latn", "hlb_Deva", "hlt_Latn", "hne_Deva", "hnn_Latn", "hno_Arab", "hns_Latn", "hoc_Orya", "hrv_Latn", "hsb_Latn", "hto_Latn", "hub_Latn", "hue_Latn", "hui_Latn", "hul_Latn", "hun_Latn", "hus_Latn", "huu_Latn", "huv_Latn", "hux_Latn", "hvn_Latn", "hwc_Latn", "hwo_Latn", "hye_Armn", "hyw_Armn", "iba_Latn", "ibb_Latn", "ibo_Latn", "icr_Latn", "ida_Latn", "idd_Latn", "idu_Latn", "ifa_Latn", "ifb_Latn", "ife_Latn", "ifk_Latn", "ifu_Latn", "ify_Latn", "igl_Latn", "ign_Latn", "ijc_Latn", "ijn_Latn", "ikk_Latn", "ikw_Latn", "ilb_Latn", "ilo_Latn", "imo_Latn", "ina_Latn", "inb_Latn", "ind_Latn", "iou_Latn", "ipi_Latn", "ipk_Latn", "iqw_Latn", "iri_Latn", "irk_Latn", "ish_Latn", "isl_Latn", "iso_Latn", "ita_Latn", "itl_Cyrl", "its_Latn", "itv_Latn", "itw_Latn", "itz_Latn", "ixl_Latn", "izr_Latn", "izz_Latn", "jac_Latn", "jal_Latn", "jam_Latn", "jav_Latn", "jax_Latn", "jbu_Latn", "jen_Latn", "jic_Latn", "jiv_Latn", "jmc_Latn", "jmd_Latn", "jmx_Latn", "jpn_Jpan", "jqr_Latn", "juk_Latn", "jun_Orya", "juo_Latn", "jvn_Latn", "kaa_Cyrl", "kab_Latn", "kac_Latn", "kai_Latn", "kaj_Latn", "kak_Latn", "kam_Latn", "kan_Knda", "kao_Latn", "kaq_Latn", "kas_Arab", "kat_Geor", "kay_Latn", "kaz_Cyrl", "kbd_Cyrl", "kbl_Latn", "kbo_Latn", "kbp_Latn", "kbq_Latn", "kbr_Latn", "kbt_Latn", "kby_Latn", "kca_Cyrl", "kcg_Latn", "kcn_Latn", "kcq_Latn", "kdc_Latn", "kde_Latn", "kdh_Latn", "kdi_Latn", "kdj_Latn", "kdl_Latn", "kdn_Latn", "kdt_Khmr", "kea_Latn", "kek_Latn", "ken_Latn", "keo_Latn", "ker_Latn", "keu_Latn", "key_Telu", "kez_Latn", "kfb_Deva", "kff_Telu", "kfk_Deva", "kfq_Deva", "kfr_Gujr", "kfw_Latn", "kfx_Deva", "kha_Latn", "khg_Tibt", "khk_Cyrl", "khm_Khmr", "khq_Latn", "khw_Arab", "kia_Latn", "kij_Latn", "kik_Latn", "kin_Latn", "kir_Cyrl", "kix_Latn", "kjb_Latn", "kjc_Latn", "kje_Latn", "kjg_Latn", "kjh_Cyrl", "kjk_Latn", "kki_Latn", "kkj_Latn", "kle_Deva", "kln_Latn", "kls_Latn", "klu_Latn", "klv_Latn", "klw_Latn", "kma_Latn", "kmd_Latn", "kml_Latn", "kmr_Arab", "kmr_Cyrl", "kmr_Latn", "kmu_Latn", "kmy_Latn", "kna_Latn", "knb_Latn", "knc_Latn", "kne_Latn", "knf_Latn", "knj_Latn", "knk_Latn", "knn_Deva", "kno_Latn", "kog_Latn", "kol_Latn", "koo_Latn", "kor_Hang", "kpo_Latn", "kpq_Latn", "kps_Latn", "kpv_Cyrl", "kpy_Cyrl", "kpz_Latn", "kqe_Latn", "kqo_Latn", "kqp_Latn", "kqr_Latn", "kqy_Ethi", "krc_Cyrl", "kri_Latn", "krj_Latn", "krl_Latn", "krr_Khmr", "krs_Latn", "kru_Deva", "krx_Latn", "ksb_Latn", "ksd_Latn", "ksf_Latn", "ksr_Latn", "kss_Latn", "ksz_Deva", "ktb_Ethi", "ktj_Latn", "kto_Latn", "kua_Latn", "kub_Latn", "kue_Latn", "kuh_Latn", "kum_Cyrl", "kur_Arab", "kus_Latn", "kvn_Latn", "kvw_Latn", "kvx_Arab", "kwd_Latn", "kwf_Latn", "kwi_Latn", "kwm_Latn", "kxc_Ethi", "kxf_Latn", "kxm_Thai", "kxp_Arab", "kyb_Latn", "kyc_Latn", "kyf_Latn", "kyg_Latn", "kyo_Latn", "kyq_Latn", "kyu_Kali", "kyx_Latn", "kyz_Latn", "kzf_Latn", "kzi_Latn", "lac_Latn", "lag_Latn", "laj_Latn", "lam_Latn", "lao_Laoo", "las_Latn", "lat_Latn", "lav_Latn", "law_Latn", "lbj_Tibt", "lbw_Latn", "lcm_Latn", "lcp_Thai", "ldb_Latn", "led_Latn", "lee_Latn", "lef_Latn", "lem_Latn", "lew_Latn", "lex_Latn", "lgg_Latn", "lgl_Latn", "lhu_Latn", "lia_Latn", "lid_Latn", "lif_Deva", "lij_Latn", "lin_Latn", "lip_Latn", "lir_Latn", "lis_Lisu", "lit_Latn", "lje_Latn", "ljp_Latn", "lkb_Latn", "lke_Latn", "lla_Latn", "lld_Latn_gherd", "lld_Latn_valbadia", "llg_Latn", "lln_Latn", "lme_Latn", "lnd_Latn", "lns_Latn", "lnu_Latn", "loa_Latn", "lob_Latn", "lok_Latn", "lom_Latn", "lon_Latn", "loq_Latn", "lrk_Arab", "lsi_Latn", "lsm_Latn", "lss_Arab", "ltg_Latn", "lth_Latn", "lto_Latn", "ltz_Latn", "lua_Latn", "luc_Latn", "lug_Latn", "luo_Latn", "lus_Latn", "lwg_Latn", "lwo_Latn", "lww_Latn", "lzz_Latn", "maa_Latn", "mab_Latn", "mad_Latn", "maf_Latn", "mag_Deva", "mah_Latn", "mai_Deva", "maj_Latn", "mak_Latn", "mal_Mlym", "mam_Latn", "maq_Latn", "mar_Deva", "mau_Latn", "maw_Latn", "max_Latn", "maz_Latn", "mbb_Latn", "mbc_Latn", "mbh_Latn", "mbj_Latn", "mbt_Latn", "mbu_Latn", "mca_Latn", "mcb_Latn", "mcd_Latn", "mcf_Latn", "mco_Latn", "mcp_Latn", "mcq_Latn", "mcu_Latn", "mcx_Latn", "mda_Latn", "mdd_Latn", "mdv_Latn", "mdy_Ethi", "med_Latn", "mee_Latn", "meh_Latn", "mej_Latn", "mek_Latn", "mel_Latn", "men_Latn", "meq_Latn", "mer_Latn", "met_Latn", "meu_Latn", "mev_Latn", "mfe_Latn", "mfh_Latn", "mfi_Latn", "mfk_Latn", "mfm_Latn", "mfn_Latn", "mfo_Latn", "mfq_Latn", "mfv_Latn", "mfy_Latn", "mfz_Latn", "mgd_Latn", "mge_Latn", "mgg_Latn", "mgh_Latn", "mgi_Latn", "mgo_Latn", "mhi_Latn", "mhk_Latn", "mhr_Cyrl", "mhu_Latn", "mhx_Latn", "mhy_Latn", "mib_Latn", "mie_Latn", "mif_Latn", "mig_Latn", "mih_Latn", "mil_Latn", "mim_Latn", "min_Latn", "mio_Latn", "mip_Latn", "miq_Latn", "mit_Latn", "miu_Latn", "miy_Latn", "miz_Latn", "mjl_Deva", "mjv_Mlym", "mkd_Cyrl", "mkf_Latn", "mki_Arab", "mkl_Latn", "mkn_Latn", "mlg_Latn", "mlq_Latn", "mlt_Latn", "mmc_Latn", "mmg_Latn", "mnb_Latn", "mne_Latn", "mnf_Latn", "mni_Beng", "mnk_Latn", "mnw_Mymr", "mnx_Latn", "moa_Latn", "mog_Latn", "mon_Cyrl", "mop_Latn", "mor_Latn", "mos_Latn", "mox_Latn", "moz_Latn", "mpg_Latn", "mpm_Latn", "mpp_Latn", "mpx_Latn", "mqb_Latn", "mqf_Latn", "mqj_Latn", "mqn_Latn", "mqy_Latn", "mri_Latn", "mrj_Cyrl", "mrr_Deva", "mrt_Latn", "mrw_Latn", "msh_Latn", "msi_Latn", "msw_Latn", "msy_Latn", "mtd_Latn", "mtj_Latn", "mto_Latn", "mtr_Deva", "mtu_Latn", "mtx_Latn", "mua_Latn", "mug_Latn", "muh_Latn", "mui_Latn", "mup_Deva", "mur_Latn", "muv_Mlym", "muy_Latn", "mve_Arab", "mvp_Latn", "mvy_Arab", "mwq_Latn", "mwv_Latn", "mxb_Latn", "mxq_Latn", "mxs_Latn", "mxt_Latn", "mxu_Latn", "mxv_Latn", "mxy_Latn", "mya_Mymr", "myb_Latn", "myk_Latn", "myv_Cyrl", "myx_Latn", "myy_Latn", "mza_Latn", "mzi_Latn", "mzj_Latn", "mzk_Latn", "mzl_Latn", "mzm_Latn", "mzw_Latn", "nab_Latn", "nag_Latn", "nal_Latn", "nan_Latn", "nap_Latn", "nas_Latn", "naw_Latn", "nbh_Latn", "nca_Latn", "ncf_Latn", "nch_Latn", "ncj_Latn", "ncl_Latn", "nco_Latn", "ncu_Latn", "ncx_Latn", "ndi_Latn", "ndj_Latn", "ndo_Latn", "ndp_Latn", "ndv_Latn", "ndy_Latn", "ndz_Latn", "neb_Latn", "nep_Deva", "new_Deva", "nfa_Latn", "nfr_Latn", "nga_Latn", "ngi_Latn", "ngl_Latn", "ngp_Latn", "ngu_Latn", "nhe_Latn", "nhg_Latn", "nhi_Latn", "nhn_Latn", "nhq_Latn", "nhu_Latn", "nhw_Latn", "nhx_Latn", "nhy_Latn", "nia_Latn", "nij_Latn", "nim_Latn", "nin_Latn", "nja_Latn", "nko_Latn", "nla_Latn", "nlc_Latn", "nld_Latn", "nlg_Latn", "nlk_Latn", "nlv_Latn", "nmg_Latn", "nmz_Latn", "nnb_Latn", "nnh_Latn", "nnq_Latn", "nnw_Latn", "noa_Latn", "nob_Latn", "nod_Thai", "noe_Deva", "nog_Cyrl", "not_Latn", "npl_Latn", "npy_Latn", "nso_Latn", "nst_Latn", "nsu_Latn", "ntm_Latn", "ntr_Latn", "nuj_Latn", "nup_Latn", "nus_Latn", "nuz_Latn", "nwb_Latn", "nxq_Latn", "nya_Latn", "nyf_Latn", "nyn_Latn", "nyo_Latn", "nyu_Latn", "nyy_Latn", "nzi_Latn", "obo_Latn", "oci_Latn", "odk_Arab", "odu_Latn", "ogo_Latn", "ojb_Cans", "ojb_Latn", "oku_Latn", "old_Latn", "omw_Latn", "onb_Latn", "ood_Latn", "orc_Latn", "orm_Latn", "oru_Arab", "ory_Orya", "oss_Cyrl", "ote_Latn", "otq_Latn", "ozm_Latn", "pab_Latn", "pad_Latn", "pag_Latn", "pam_Latn", "pan_Guru", "pao_Latn", "pap_Latn", "pau_Latn", "pbb_Latn", "pbc_Latn", "pbi_Latn", "pbs_Latn", "pbt_Arab", "pbu_Arab", "pce_Thai", "pcm_Latn", "pex_Latn", "pez_Latn", "phl_Arab", "phr_Arab", "pib_Latn", "pil_Latn", "pip_Latn", "pir_Latn", "pis_Latn", "piy_Latn", "pjt_Latn", "pkb_Latn", "pko_Latn", "plk_Arab", "pls_Latn", "plt_Latn", "plw_Latn", "pmf_Latn", "pmq_Latn", "pms_Latn", "pmy_Latn", "pnb_Arab", "pne_Latn", "pny_Latn", "poc_Latn", "poe_Latn", "poh_Latn", "poi_Latn", "pol_Latn", "por_Latn", "pov_Latn", "pow_Latn", "poy_Latn", "ppk_Latn", "pps_Latn", "prf_Latn", "prk_Latn", "prq_Latn", "prt_Thai", "pse_Latn", "pss_Latn", "pst_Arab", "ptu_Latn", "pua_Latn", "pui_Latn", "pus_Arab", "pwg_Latn", "pwn_Latn", "pww_Thai", "pxm_Latn", "qub_Latn", "quc_Latn", "quf_Latn", "qug_Latn", "quh_Latn", "qul_Latn", "qum_Latn", "qup_Latn", "qur_Latn", "qus_Latn", "quv_Latn", "quw_Latn", "qux_Latn", "quy_Latn", "quz_Latn", "qva_Latn", "qvc_Latn", "qve_Latn", "qvh_Latn", "qvi_Latn", "qvj_Latn", "qvl_Latn", "qvm_Latn", "qvn_Latn", "qvo_Latn", "qvs_Latn", "qvw_Latn", "qvz_Latn", "qwa_Latn", "qwh_Latn", "qws_Latn", "qxa_Latn", "qxh_Latn", "qxl_Latn", "qxn_Latn", "qxo_Latn", "qxp_Latn", "qxr_Latn", "qxt_Latn", "qxu_Latn", "qxw_Latn", "rag_Latn", "rah_Beng", "rai_Latn", "rap_Latn", "rav_Deva", "raw_Latn", "rej_Latn", "rel_Latn", "rgu_Latn", "rhg_Latn", "rif_Arab", "rif_Latn", "rim_Latn", "rjs_Deva", "rkt_Beng", "rmc_Cyrl", "rmc_Latn", "rmo_Latn", "rmy_Cyrl", "rmy_Latn", "rng_Latn", "rnl_Latn", "rob_Latn", "rof_Latn", "roh_Latn_surs1244", "rol_Latn", "ron_Latn", "roo_Latn", "rop_Latn", "rro_Latn", "rth_Latn", "rub_Latn", "ruc_Latn", "ruf_Latn", "rug_Latn", "run_Latn", "rus_Cyrl", "rwm_Latn", "rwr_Deva", "sab_Latn", "sag_Latn", "sah_Cyrl", "saj_Latn", "saq_Latn", "sas_Latn", "sau_Latn", "say_Latn", "sba_Latn", "sbd_Latn", "sbl_Latn", "sbn_Arab", "sbp_Latn", "sch_Latn", "sck_Deva", "scl_Arab", "scn_Latn", "sco_Latn", "sda_Latn", "sdo_Latn", "sea_Latn", "seh_Latn", "sei_Latn", "ses_Latn", "sey_Latn", "sgb_Latn", "sgj_Deva", "sgw_Ethi", "shi_Latn", "shk_Latn", "shn_Mymr", "sho_Latn", "shp_Latn", "sid_Latn", "sig_Latn", "sil_Latn", "sin_Sinh", "sip_Tibt", "siw_Latn", "sja_Latn", "sjm_Latn", "sjp_Deva", "sjr_Latn", "skg_Latn", "skr_Arab", "sld_Latn", "slk_Latn", "slu_Latn", "slv_Latn", "sml_Latn", "smo_Latn", "sna_Latn", "snc_Latn", "snd_Arab", "sne_Latn", "snk_Latn", "snn_Latn", "snp_Latn", "snv_Latn", "snw_Latn", "sol_Latn", "som_Latn", "soy_Latn", "spa_Latn", "spp_Latn", "sps_Latn", "spy_Latn", "src_Latn", "srd_Latn", "sri_Latn", "srm_Latn", "srn_Latn", "sro_Latn", "srp_Cyrl", "srr_Latn", "srx_Deva", "ssi_Arab", "ste_Latn", "stn_Latn", "stp_Latn", "sua_Latn", "suc_Latn", "suk_Latn", "sun_Latn", "sur_Latn", "sus_Latn", "suv_Latn", "suz_Deva", "sva_Geor", "swe_Latn", "swh_Latn", "swv_Deva", "sxb_Latn", "sxn_Latn", "sya_Latn", "syl_Latn", "sza_Latn", "szy_Latn", "tac_Latn", "taj_Deva", "tam_Taml", "tan_Latn", "tao_Latn", "tap_Latn", "taq_Latn", "tar_Latn", "tat_Cyrl", "tav_Latn", "tay_Latn", "tbc_Latn", "tbf_Latn", "tbg_Latn", "tbk_Latn", "tbl_Latn", "tby_Latn", "tbz_Latn", "tca_Latn", "tcc_Latn", "tcf_Latn", "tcy_Mlym", "tcz_Latn", "tdj_Latn", "tdn_Latn", "tdx_Latn", "ted_Latn", "tee_Latn", "tel_Telu", "tem_Latn", "teo_Latn", "ter_Latn", "tew_Latn", "tex_Latn", "tfr_Latn", "tgc_Latn", "tgj_Latn", "tgk_Cyrl", "tgl_Latn", "tgo_Latn", "tgp_Latn", "tha_Thai", "the_Deva", "thk_Latn", "thl_Deva", "thq_Deva", "thr_Deva", "thv_Tfng", "tig_Ethi", "tih_Latn", "tik_Latn", "tio_Latn", "tir_Ethi", "tkg_Latn", "tkr_Latn", "tkt_Deva", "tlb_Latn", "tli_Latn", "tlj_Latn", "tlp_Latn", "tly_Latn", "tmc_Latn", "tmf_Latn", "tna_Latn", "tng_Latn", "tnk_Latn", "tnn_Latn", "tnp_Latn", "tnr_Latn", "tnt_Latn", "tob_Latn", "toc_Latn", "toh_Latn", "tok_Latn", "tom_Latn", "top_Latn", "tos_Latn", "tpi_Latn", "tpl_Latn", "tpm_Latn", "tpp_Latn", "tpt_Latn", "tpz_Latn", "tqp_Latn", "trc_Latn", "tri_Latn", "trn_Latn", "trp_Latn", "trq_Latn", "trs_Latn", "trv_Latn", "trw_Arab", "tsn_Latn", "tso_Latn", "tsz_Latn", "ttc_Latn", "tte_Latn", "ttj_Latn", "ttq_Tfng", "ttr_Latn", "ttu_Latn", "tue_Latn", "tuf_Latn", "tui_Latn", "tuk_Arab", "tuk_Latn", "tul_Latn", "tuo_Latn", "tuq_Latn", "tur_Latn", "tuv_Latn", "tuy_Latn", "tvo_Latn", "tvu_Latn", "tvw_Latn", "twb_Latn", "twe_Latn", "twu_Latn", "txa_Latn", "txq_Latn", "txs_Latn", "txu_Latn", "txy_Latn", "tye_Latn", "tzh_Latn", "tzj_Latn", "tzo_Latn", "ubl_Latn", "ubu_Latn", "udl_Latn", "udm_Cyrl", "udu_Latn", "uig_Arab", "uig_Cyrl", "uki_Orya", "ukr_Cyrl", "ukv_Latn", "umb_Latn", "upv_Latn", "ura_Latn", "urb_Latn", "urd_Arab", "urd_Deva", "urd_Latn", "urh_Latn", "urk_Thai", "urt_Latn", "ury_Latn", "ush_Arab", "usp_Latn", "uzb_Cyrl", "uzb_Latn", "uzn_Latn", "vag_Latn", "vah_Deva", "vai_Latn", "var_Latn", "ver_Latn", "vid_Latn", "vie_Latn", "vif_Latn", "vmc_Latn", "vmj_Latn", "vmm_Latn", "vmp_Latn", "vmw_Latn", "vmy_Latn", "vmz_Latn", "vro_Latn", "vun_Latn", "vut_Latn", "wal_Ethi", "wal_Latn", "wap_Latn", "war_Latn", "waw_Latn", "way_Latn", "wba_Latn", "wbl_Latn", "wbr_Deva", "wci_Latn", "weo_Latn", "wes_Latn", "wja_Latn", "wji_Latn", "wlo_Latn", "wlx_Latn", "wmw_Latn", "wob_Latn", "wof_Latn", "wol_Latn", "wsg_Telu", "wwa_Latn", "xal_Cyrl", "xdy_Latn", "xed_Latn", "xer_Latn", "xhe_Arab", "xho_Latn", "xka_Arab", "xkl_Latn", "xmf_Geor", "xmm_Latn", "xmv_Latn", "xnj_Latn", "xnr_Deva", "xog_Latn", "xon_Latn", "xpe_Latn", "xrb_Latn", "xsb_Latn", "xsm_Latn", "xsr_Deva", "xsu_Latn", "xta_Latn", "xtd_Latn", "xte_Latn", "xti_Latn", "xtm_Latn", "xtn_Latn", "xtu_Latn", "xua_Taml", "xuo_Latn", "yaa_Latn", "yad_Latn", "yal_Latn", "yam_Latn", "yao_Latn", "yaq_Latn", "yas_Latn", "yat_Latn", "yav_Latn", "yay_Latn", "yaz_Latn", "yba_Latn", "ybb_Latn", "ycl_Latn", "ycn_Latn", "ydd_Hebr", "ydg_Arab", "yea_Mlym", "yer_Latn", "yes_Latn", "yka_Latn", "yli_Latn", "yor_Latn", "yre_Latn", "yua_Latn", "yue_Hans", "yue_Hant", "yuz_Latn", "yva_Latn", "zaa_Latn", "zab_Latn", "zac_Latn", "zad_Latn", "zae_Latn", "zai_Latn", "zam_Latn", "zao_Latn", "zaq_Latn", "zar_Latn", "zas_Latn", "zav_Latn", "zaw_Latn", "zca_Latn", "zga_Latn", "zim_Latn", "ziw_Latn", "zmz_Latn", "zne_Latn", "zoc_Latn", "zoh_Latn", "zor_Latn", "zos_Latn", "zpc_Latn", "zpg_Latn", "zpi_Latn", "zpl_Latn", "zpm_Latn", "zpo_Latn", "zpt_Latn", "zpu_Latn", "zpv_Latn", "zpy_Latn", "zpz_Latn", "zsm_Latn", "ztg_Latn", "ztn_Latn", "ztp_Latn", "ztq_Latn", "zts_Latn", "ztu_Latn", "zty_Latn", "zul_Latn", "zyb_Latn", "zyp_Latn", "zza_Latn",
}  # fmt: skip


class AsrModels(Enum):
    whisper_large_v2 = "Whisper Large v2 (openai)"
    whisper_large_v3 = "Whisper Large v3 (openai)"
    gpt_4_o_audio = "GPT-4o (openai)"
    gpt_4_o_mini_audio = "GPT-4o mini (openai)"
    gcp_v1 = "Google Cloud V1"
    usm = "Chirp / USM (Google V2)"
    deepgram = "Deepgram"
    azure = "Azure Speech"
    elevenlabs = "ElevenLabs Scribe v1"
    seamless_m4t_v2 = "Seamless M4T v2 (Facebook Research)"
    mms_1b_all = "Massively Multilingual Speech (MMS) (Facebook Research)"
    meta_omnilingual_asr_llm_7b = "Omnilingual ASR LLM (Meta)"

    ghana_nlp_asr_v2 = "Ghana NLP ASR v2"
    lelapa = "Vulavula (Lelapa AI)"
    whisper_sunbird_large_v3 = "Sunbird Ugandan Whisper v3 (Sunbird AI)"
    whisper_akera_large_v3 = "Kikuyu v2 Whisper (akera)"
    whisper_swahili_medium_v3 = "Jacaranda Health Swahili Whisper v3 (Jacaranda Health)"
    mbaza_ctc_large = "Mbaza Conformer LG (MbazaNLP)"

    seamless_m4t = "Seamless M4T [Deprecated] (Facebook Research)"
    whisper_chichewa_large_v3 = (
        "Whisper Large v3 chichewa [Deprecated] (opportunity.org)"
    )
    nemo_english = "Conformer English [Deprecated] (ai4bharat.org)"
    nemo_hindi = "Conformer Hindi [Deprecated] (ai4bharat.org)"
    whisper_hindi_large_v2 = "Whisper Hindi Large v2 [Deprecated] (Bhashini)"
    whisper_telugu_large_v2 = "Whisper Telugu Large v2 [Deprecated] (Bhashini)"
    vakyansh_bhojpuri = "Vakyansh Bhojpuri [Deprecated] (Open-Speech-EkStep)"

    def supports_auto_detect(self) -> bool:
        return self not in {
            self.azure,
            self.gcp_v1,
            self.mms_1b_all,
            self.seamless_m4t_v2,
            self.ghana_nlp_asr_v2,
        }

    @classmethod
    def _deprecated(cls):
        return {
            cls.seamless_m4t,
            cls.whisper_chichewa_large_v3,
            cls.nemo_english,
            cls.nemo_hindi,
            cls.whisper_hindi_large_v2,
            cls.whisper_telugu_large_v2,
            cls.vakyansh_bhojpuri,
        }

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls[key]
        except KeyError:
            return default

    def supports_speech_translation(self) -> bool:
        return self in {
            self.seamless_m4t_v2,
            self.whisper_large_v2,
            self.whisper_large_v3,
        }

    def supports_input_prompt(self) -> bool:
        return self in {self.gpt_4_o_audio, self.gpt_4_o_mini_audio}


asr_model_ids = {
    AsrModels.whisper_akera_large_v3: "akera/whisper-large-v3-kik-full_v2",
    AsrModels.gpt_4_o_audio: "gpt-4o-transcribe",
    AsrModels.gpt_4_o_mini_audio: "gpt-4o-mini-transcribe",
    AsrModels.whisper_large_v3: "vaibhavs10/incredibly-fast-whisper:3ab86df6c8f54c11309d4d1f930ac292bad43ace52d10c80d87eb258b3c9f79c",
    AsrModels.whisper_large_v2: "openai/whisper-large-v2",
    AsrModels.whisper_hindi_large_v2: "vasista22/whisper-hindi-large-v2",
    AsrModels.whisper_telugu_large_v2: "vasista22/whisper-telugu-large-v2",
    AsrModels.whisper_chichewa_large_v3: "dmatekenya/whisper-large-v3-chichewa",
    AsrModels.vakyansh_bhojpuri: "Harveenchadha/vakyansh-wav2vec2-bhojpuri-bhom-60",
    AsrModels.nemo_english: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/english_large_data_fixed.nemo",
    AsrModels.nemo_hindi: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/stt_hi_conformer_ctc_large_v2.nemo",
    AsrModels.seamless_m4t_v2: "facebook/seamless-m4t-v2-large",
    AsrModels.mms_1b_all: "facebook/mms-1b-all",
    AsrModels.meta_omnilingual_asr_llm_7b: "omniASR_LLM_7B",
    AsrModels.lelapa: "lelapa-vulavula",
    AsrModels.elevenlabs: "elevenlabs-scribe-v1",
    AsrModels.whisper_sunbird_large_v3: "Sunbird/asr-whisper-large-v3-salt",
    AsrModels.whisper_swahili_medium_v3: "Jacaranda-Health/ASR-STT",
    AsrModels.mbaza_ctc_large: "mbazaNLP/stt_rw_sw_lg_conformer_ctc_large",
}

forced_asr_languages = {
    AsrModels.whisper_hindi_large_v2: "hi",
    AsrModels.whisper_telugu_large_v2: "te",
    AsrModels.whisper_chichewa_large_v3: "shona",
    AsrModels.vakyansh_bhojpuri: "bho",
    AsrModels.nemo_english: "en",
    AsrModels.nemo_hindi: "hi",
    AsrModels.whisper_akera_large_v3: "kik",
}

asr_supported_languages = {
    AsrModels.whisper_large_v3: WHISPER_LARGE_V3_SUPPORTED,
    AsrModels.gpt_4_o_audio: WHISPER_LARGE_V2_SUPPORTED,  # https://platform.openai.com/docs/guides/speech-to-text#supported-languages
    AsrModels.gpt_4_o_mini_audio: WHISPER_LARGE_V2_SUPPORTED,
    AsrModels.whisper_large_v2: WHISPER_LARGE_V2_SUPPORTED,
    AsrModels.whisper_telugu_large_v2: {"te"},
    AsrModels.whisper_chichewa_large_v3: {"shona"},
    AsrModels.whisper_hindi_large_v2: {"hi"},
    AsrModels.vakyansh_bhojpuri: {"bho"},
    AsrModels.nemo_english: {"en"},
    AsrModels.nemo_hindi: {"hi"},
    AsrModels.gcp_v1: GCP_V1_SUPPORTED,
    AsrModels.usm: CHIRP_SUPPORTED,
    AsrModels.deepgram: DEEPGRAM_SUPPORTED,
    AsrModels.elevenlabs: ELEVENLABS_SUPPORTED,
    AsrModels.seamless_m4t_v2: SEAMLESS_v2_ASR_SUPPORTED,
    AsrModels.azure: AZURE_SUPPORTED,
    AsrModels.mms_1b_all: MMS_SUPPORTED,
    AsrModels.meta_omnilingual_asr_llm_7b: OMNILINGUAL_ASR_SUPPORTED,
    AsrModels.ghana_nlp_asr_v2: GHANA_NLP_ASR_V2_SUPPORTED,
    AsrModels.lelapa: LELAPA_ASR_SUPPORTED,
    AsrModels.whisper_sunbird_large_v3: SUNBIRD_SUPPORTED_LANGUAGES,
    AsrModels.whisper_swahili_medium_v3: {"sw", "en"},
    AsrModels.whisper_akera_large_v3: {"kik"},
    AsrModels.mbaza_ctc_large: {"sw", "rw", "lg"},
}


class AsrChunk(typing_extensions.TypedDict):
    timestamp: tuple[float, float]
    text: str
    speaker: int | None


class AsrOutputJson(typing_extensions.TypedDict):
    text: str
    chunks: typing_extensions.NotRequired[list[AsrChunk]]


class AsrOutputFormat(Enum):
    text = "Text"
    json = "JSON"
    srt = "SRT"
    vtt = "VTT"


class TranslationModel(typing.NamedTuple):
    label: str
    supports_glossary: bool = False
    supports_auto_detect: bool = False
    is_asr_model: bool = False


class TranslationModels(TranslationModel, Enum):
    google = TranslationModel(
        label="Google Translate",
        supports_glossary=True,
        supports_auto_detect=True,
    )
    ghana_nlp = TranslationModel(label="Ghana NLP Translate")
    lelapa = TranslationModel(label="Vulavula (Lelapa AI)")
    whisper_large_v2 = TranslationModel(
        label="Whisper Large v2 (inbuilt)", is_asr_model=True
    )
    whisper_large_v3 = TranslationModel(
        label="Whisper Large v3 (inbuilt)", is_asr_model=True
    )
    seamless_m4t_v2 = TranslationModel(
        label="Seamless M4T v2 (inbuilt)", is_asr_model=True
    )

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls[key]
        except KeyError:
            return default

    @classmethod
    def target_languages_by_model(cls) -> dict[TranslationModel, typing.Iterable[str]]:
        return {e: e.supported_target_languages() for e in cls if not e.is_asr_model}

    def supported_target_languages(self) -> typing.Iterable[str]:
        match self:
            case self.google:
                return google_translate_target_languages().keys()
            case self.ghana_nlp:
                return (
                    ghana_nlp_translate_target_languages().keys()
                    if settings.GHANA_NLP_SUBKEY
                    else []
                )
            case self.seamless_m4t_v2:
                return SEAMLESS_v2_ASR_SUPPORTED
            case self.lelapa:
                return LELAPA_MT_SUPPORTED
            case _:
                return ["en"]


def translation_language_selector(
    *,
    model: TranslationModels | None,
    label: str,
    key: str,
    language_filter: str = "",
    sort_by: str | None = None,
    **kwargs,
) -> str | None:
    if not model:
        gui.session_state[key] = None
        return

    allow_none = (
        kwargs.pop("allow_none", None)
        and model.supports_auto_detect
        and not language_filter
    )

    options = list(model.supported_target_languages())
    if language_filter:
        options = filter_languages(language_filter, options)
    else:
        sort_language_options(options, sort_by)

    return gui.selectbox(
        label=label,
        key=key,
        format_func=lang_format_func,
        options=options,
        allow_none=allow_none,
        **kwargs,
    )


def translation_model_selector(
    key: str = "translation_model",
    allow_none: bool = True,
    *,
    language_filter: str = "",
    asr_model: AsrModels | None = None,
) -> TranslationModels | None:
    from daras_ai_v2.enum_selector_widget import enum_selector

    if language_filter:
        supported_models = filter_models_by_language(
            language_filter, TranslationModels.target_languages_by_model()
        )
    else:
        supported_models = [
            model for model in TranslationModels if not model.is_asr_model
        ]

    # insert in-built model if available
    in_built_option = TranslationModels.get(asr_model.name) if asr_model else None
    if in_built_option and in_built_option not in supported_models:
        supported_models.append(in_built_option)

    # @TODO set state to inbuilt model if some other value is set
    # prev_model = gui.session_state.get(key)
    # if in_built_option and prev_model != in_built_option:
    #     gui.session_state[key] = in_built_option

    if not supported_models:
        gui.session_state[key] = None
        gui.error("No translation model available for the selected language.", icon="⚠️")
        return

    # Select the model using enum_selector
    model = enum_selector(
        supported_models,
        "###### Translation Model",
        allow_none=allow_none,
        use_selectbox=True,
        key=key,
    )
    if model:
        return TranslationModels[model]
    else:
        return None


def google_translate_language_selector(
    label="""
    ###### Google Translate (*optional*)
    """,
    key="google_translate_target",
    allow_none=True,
    **kwargs,
):
    """
    Streamlit widget for selecting a language for Google Translate.
    Args:
        label: the label to display
        key: the key to save the selected language to in the session state
    """
    languages = google_translate_target_languages()
    options = list(languages.keys())
    return gui.selectbox(
        label=label,
        key=key,
        format_func=lambda k: languages[k] if k else "———",
        options=options,
        allow_none=allow_none,
        **kwargs,
    )


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def ghana_nlp_translate_target_languages():
    """
    Get list of supported languages for Ghana NLP Translation.
    :return: Dictionary of language codes and display names.
    Reference: https://translation.ghananlp.org/api-details#api=ghananlp-translation-webservice-api
    """
    r = requests.get(
        "https://translation-api.ghananlp.org/v1/languages",
        headers=GHANA_API_AUTH_HEADERS,
    )
    raise_for_status(r)
    return r.json().get("languages") or {}


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def google_translate_target_languages() -> dict[str, str]:
    """
    Get list of supported languages for Google Translate.
    :return: Dictionary of language codes and display names.
    """
    from google.cloud import translate_v3 as translate

    _, project = get_google_auth_session()
    parent = f"projects/{project}/locations/global"
    client = translate.TranslationServiceClient()
    supported_languages = client.get_supported_languages(
        parent=parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_target
    }


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def google_translate_source_languages() -> dict[str, str]:
    """
    Get list of supported languages for Google Translate.
    :return: Dictionary of language codes and display names.
    """
    from google.cloud import translate_v3 as translate

    _, project = get_google_auth_session()
    parent = f"projects/{project}/locations/global"
    client = translate.TranslationServiceClient()
    supported_languages = client.get_supported_languages(
        parent=parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_source
    }


def asr_model_selector(
    key: str = "asr_model",
    *,
    language_filter: str = "",
    label: str = "###### Speech Recognition Model",
    use_selectbox: bool = True,
    **kwargs,
) -> AsrModels | None:
    if language_filter:
        supported_models = filter_models_by_language(
            language_filter, asr_supported_languages
        )
    else:
        supported_models = AsrModels
    model = enum_selector(
        supported_models,
        label=label,
        key=key,
        use_selectbox=use_selectbox,
        **kwargs,
    )
    if model:
        return AsrModels[model]
    else:
        return None


def asr_language_selector(
    selected_model: AsrModels,
    label: str = "###### Spoken Language",
    key: str = "language",
    *,
    language_filter: str = "",
    sort_by: str | None = None,
):
    # don't show language selector for models with forced language
    forced_lang = forced_asr_languages.get(selected_model)
    if forced_lang:
        gui.session_state[key] = forced_lang
        return forced_lang

    allow_none = (
        selected_model and selected_model.supports_auto_detect() and not language_filter
    )

    options = list(asr_supported_languages.get(selected_model, []))
    if language_filter:
        # filter the languages to show dialects only from selected languages
        options = filter_languages(language_filter, options)
    else:
        sort_language_options(options, sort_by)

    # handle non-canonical language codes
    old_lang = gui.session_state.get(key)
    if old_lang:
        try:
            gui.session_state[key] = normalised_lang_in_collection(old_lang, options)
        except UserError:
            gui.session_state[key] = None

    return gui.selectbox(
        label=label,
        key=key,
        format_func=lang_format_func,
        options=options,
        allow_none=allow_none,
    )


def sort_language_options(options: list[str | None], sort_by: str | None):
    sort_by = sort_by or "en"
    options.sort(key=lambda tag: tag and are_languages_same(tag, sort_by), reverse=True)


def language_filter_selector(
    *,
    options: list[str],
    label: str = '<i class="fa-sharp-duotone fa-solid fa-bars-filter"></i> &nbsp; Filter by Language',
    key: str = "language_filter",
) -> str:
    clear_key = key + ":clear"
    if gui.session_state.pop(clear_key, None):
        gui.session_state[key] = None

    with gui.div(className="d-flex align-items-center"):
        if label:
            with gui.div(className="me-3 text-muted"):
                gui.caption(label, unsafe_allow_html=True)

        with gui.div(style=dict(minWidth="200px")):
            language_filter = gui.selectbox(
                label="",
                label_visibility="collapsed",
                key=key,
                format_func=lambda tag: lang_format_func(tag, default="All Languages"),
                options=options,
                allow_none=True,
            )

        if language_filter:
            gui.button(
                '<i class="fa-solid fa-circle-xmark"></i>',
                type="tertiary",
                key=clear_key,
                className="px-2 py-1 ms-1",
            )

    return language_filter


def lang_format_func(tag: str, *, default: str = "Auto Detect") -> str:
    import langcodes

    if not tag:
        return default
    try:
        return f"{langcodes.Language.get(tag).display_name()} | {tag}"
    except langcodes.LanguageTagError:
        return tag


def run_translate(
    texts: list[str],
    target_language: str,
    source_language: str | None = None,
    glossary_url: str | None = None,
    model: str = TranslationModels.google.name,
):
    if not model:
        return texts

    if model == TranslationModels.google.name:
        return run_google_translate(
            texts=texts,
            target_language=target_language,
            source_language=source_language,
            glossary_url=glossary_url,
        )
    elif model == TranslationModels.ghana_nlp.name:
        return run_ghana_nlp_translate(
            texts=texts,
            target_language=target_language,
            source_language=source_language,
        )
    elif model == TranslationModels.lelapa.name:
        return run_lelapa_translate(
            texts=texts,
            target_language=target_language,
            source_language=source_language,
        )
    else:
        raise ValueError("Unsupported translation model: " + str(model))


def run_ghana_nlp_translate(
    texts: list[str], target_language: str, source_language: str
) -> list[str]:
    assert source_language and target_language, (
        "Both Source & Target language is required for Ghana NLP"
    )
    source_language = normalised_lang_in_collection(
        source_language, ghana_nlp_translate_target_languages()
    )
    target_language = normalised_lang_in_collection(
        target_language, ghana_nlp_translate_target_languages()
    )
    if source_language == target_language:
        return texts
    return map_parallel(
        lambda doc: _call_ghana_nlp_chunked(doc, source_language, target_language),
        texts,
        max_workers=TRANSLATE_BATCH_SIZE,
    )


def _call_ghana_nlp_chunked(
    text: str, source_language: str, target_language: str
) -> str:
    return "".join(
        map_parallel(
            lambda doc: _call_ghana_nlp_raw(doc.text, source_language, target_language),
            text_splitter(text, chunk_size=GHANA_NLP_MAXLEN, length_function=len),
            max_workers=TRANSLATE_BATCH_SIZE,
        )
    )


def _call_ghana_nlp_raw(text: str, source_language: str, target_language: str) -> str:
    r = requests.post(
        "https://translation-api.ghananlp.org/v1/translate",
        headers=GHANA_API_AUTH_HEADERS,
        json={"in": text, "lang": source_language + "-" + target_language},
    )
    raise_for_status(r)
    return r.json()


def run_lelapa_translate(
    texts: list[str], target_language: str, source_language: str
) -> list[str]:
    assert source_language and target_language, (
        "Both Source & Target language are required"
    )
    return map_parallel(
        lambda text: _call_lelapa_translate_raw(text, source_language, target_language),
        texts,
        max_workers=TRANSLATE_BATCH_SIZE,
    )


def _call_lelapa_translate_raw(
    text: str, source_language: str, target_language: str
) -> str:
    r = requests.post(
        "https://vulavula-services.lelapa.ai/api/v1/translate/process",
        headers={"X-CLIENT-TOKEN": settings.LELAPA_API_KEY},
        json={
            "input_text": text,
            "source_lang": source_language,
            "target_lang": target_language,
        },
    )
    raise_for_status(r)
    return r.json()["translation"][0]["translated_text"]  # yes


def run_google_translate(
    texts: list[str],
    target_language: str,
    source_language: str | None = None,
    glossary_url: str | None = None,
) -> list[str]:
    """
    Translate text using the Google Translate API.
    Args:
        texts (list[str]): Text to be translated.
        target_language (str): Language code to translate to.
        source_language (str): Language code to translate from.
        glossary_url (str): URL of glossary file.
    Returns:
        list[str]: Translated text.
    """
    from google.cloud import translate_v2 as translate

    supported_languages = google_translate_target_languages()
    if source_language:
        try:
            source_language = normalised_lang_in_collection(
                source_language, supported_languages
            )
        except UserError:
            source_language = None  # autodetect
    target_language = normalised_lang_in_collection(
        target_language, supported_languages
    )

    # if the language supports transliteration, we should check if the script is Latin
    if source_language and source_language not in TRANSLITERATION_SUPPORTED:
        detected_source_languges = [source_language] * len(texts)
    else:
        translate_client = translate.Client()
        detections = flatten(
            translate_client.detect_language(texts[i : i + TRANSLATE_BATCH_SIZE])
            for i in range(0, len(texts), TRANSLATE_BATCH_SIZE)
        )
        detected_source_languges = [detection["language"] for detection in detections]

    # fix for when sometimes google might detect a different language than the user provided one
    if source_language:
        detected_source_languges = [
            code if source_language in code.split("-")[0] else source_language
            for code in detected_source_languges
        ]

    return map_parallel(
        lambda text, src_lang: _translate_text(
            text, target_language, src_lang, glossary_url
        ),
        texts,
        detected_source_languges,
        max_workers=TRANSLATE_BATCH_SIZE,
    )


def _translate_text(
    text: str,
    target_language: str,
    source_language: str,
    glossary_url: str | None,
) -> str:
    is_romanized = source_language.endswith("-Latn")
    source_language = source_language.split("-")[0]
    enable_transliteration = (
        is_romanized and source_language in TRANSLITERATION_SUPPORTED
    )

    # prevent incorrect API calls
    if not text or source_language == target_language or source_language == "und":
        return text

    config = {
        "target_language_code": target_language,
        "contents": text,
        "mime_type": "text/plain",
        "transliteration_config": {"enable_transliteration": enable_transliteration},
    }
    if source_language != "auto":
        config["source_language_code"] = source_language

    if glossary_url and not enable_transliteration:
        from glossary_resources.models import GlossaryResource

        gr = GlossaryResource.objects.get_or_create_from_url(glossary_url)[0]
        GlossaryResource.objects.filter(pk=gr.pk).update(
            usage_count=F("usage_count") + 1
        )
        location = gr.location
        config["glossary_config"] = {
            "glossary": gr.get_glossary_path(),
            "ignoreCase": True,
        }
    else:
        location = "global"

    authed_session, project = get_google_auth_session()
    res = authed_session.post(
        f"https://translation.googleapis.com/v3/projects/{project}/locations/{location}:translateText",
        json=config,
    )
    raise_for_status(res)
    data = res.json()
    try:
        result = data["glossaryTranslations"][0]["translatedText"]
    except (KeyError, IndexError):
        result = data["translations"][0]["translatedText"]
    return result.strip()


def _MinT_translate_one_text(
    text: str, source_language: str, target_language: str
) -> str:
    import langcodes

    source_language = langcodes.Language.get(source_language).language
    target_language = langcodes.Language.get(target_language).language
    res = requests.post(
        f"https://translate.wmcloud.org/api/translate/{source_language}/{target_language}",
        json={"text": text},
    )
    raise_for_status(res)

    # e.g. {"model":"IndicTrans2_indec_en","sourcelanguage":"hi","targetlanguage":"en","translation":"hello","translationtime":0.8}
    tanslation = res.json()
    return tanslation.get("translation", text)


_session_lock = threading.Lock()


@lru_cache
def get_google_auth_session(*scopes: str) -> tuple[AuthorizedSession, str]:
    if not scopes:
        scopes = ("https://www.googleapis.com/auth/cloud-platform",)
    with _session_lock:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, project = google.auth.default(scopes=scopes)
        # AuthorizedSession takes care of refreshing the token and adding it to request headers
        return AuthorizedSession(credentials=creds), project


def elevenlabs_asr(audio_url: str, language: str = None) -> dict:
    """
    Call ElevenLabs Speech-to-Text API
    """
    audio_r = requests.get(audio_url)
    raise_for_status(audio_r, is_user_url=True)

    # Set up the files and form data for the multipart request
    files = {"file": audio_r.content}
    data = {"model_id": "scribe_v1"}
    headers = {"xi-api-key": settings.ELEVEN_LABS_API_KEY}

    # Language parameter is sent in the form data
    if language:
        data["language_code"] = language

    response = requests.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        files=files,
        headers=headers,
        data=data,
    )
    raise_for_status(response)

    return response.json()


def run_asr(
    audio_url: str,
    selected_model: str,
    language: str = None,
    output_format: str = "text",
    speech_translation_target: str | None = None,
    input_prompt: str | None = None,
) -> str | AsrOutputJson:
    """
    Run ASR on audio.
    Args:
        audio_url (str): url of audio to be transcribed.
        selected_model (str): ASR model to use.
        language: language of the audio
        output_format: format of the output
        speech_translation_target: Speech Translation
    Returns:
        str: Transcribed text.
    """
    import google.cloud.speech_v2 as cloud_speech
    from google.api_core.client_options import ClientOptions
    from google.cloud.texttospeech_v1 import AudioEncoding
    import langcodes

    selected_model = AsrModels[selected_model]
    if selected_model in AsrModels._deprecated():
        raise UserError(f"Model {selected_model} is deprecated.")
    output_format = AsrOutputFormat[output_format]
    audio_url, size = audio_url_to_wav_url(audio_url)
    is_short = size < SHORT_FILE_CUTOFF

    if selected_model == AsrModels.azure:
        return azure_asr(audio_url, language)
    elif selected_model == AsrModels.elevenlabs:
        result = elevenlabs_asr(audio_url, language)
        chunks = []
        for word_data in result.get("words", []):
            if word_data.get("type") == "word":
                speaker = word_data.get("speaker_id", 0)
            else:
                speaker = None
            chunk = {
                "timestamp": (word_data["start"], word_data["end"]),
                "text": word_data["text"],
                "speaker": speaker,
            }
            chunks.append(chunk)
        data = {"text": result["text"], "chunks": chunks}
    elif selected_model == AsrModels.whisper_large_v3:
        import replicate

        config = {
            "audio": audio_url,
            "return_timestamps": output_format != AsrOutputFormat.text,
            "task": "translate" if speech_translation_target else "transcribe",
        }
        if language:
            config["language"] = WHISPER_LARGE_V3_SUPPORTED[
                normalised_lang_in_collection(language, WHISPER_LARGE_V3_SUPPORTED)
            ]
        data = replicate.run(
            asr_model_ids[AsrModels.whisper_large_v3],
            input=config,
        )
    elif selected_model == AsrModels.deepgram:
        r = requests.post(
            "https://api.deepgram.com/v1/listen",
            headers={
                "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
            },
            params={
                "tier": "nova",
                "model": "general",  # "phonecall"
                "diarize": "true",
                "language": language,
                "detect_language": "true" if language else "false",
                "punctuate": "true",
            },
            json={
                "url": audio_url,
            },
        )
        raise_for_status(r)
        data = r.json()
        result = data["results"]["channels"][0]["alternatives"][0]
        chunk = None
        chunks = []
        for word in result["words"]:
            if not chunk or word["speaker"] != chunk["speaker"]:
                chunk = {
                    "speaker": word["speaker"],
                    "text": word["word"],
                    "timestamp": word["start"],
                }
                chunks.append(chunk)
            else:
                chunk["text"] += " " + word["word"]
        return "\n".join(
            f"Speaker {chunk['speaker']}: {chunk['text']}" for chunk in chunks
        )
    elif selected_model == AsrModels.seamless_m4t_v2:
        data = call_celery_task(
            "seamless.asr",
            pipeline=dict(
                model_id=asr_model_ids[AsrModels.seamless_m4t_v2],
            ),
            inputs=dict(
                audio=audio_url,
                src_lang=language,
                tgt_lang=(
                    speech_translation_target
                    and normalised_lang_in_collection(
                        speech_translation_target, SEAMLESS_v2_ASR_SUPPORTED
                    )
                ),
            ),
        )
    elif selected_model == AsrModels.gcp_v1:
        return gcp_asr_v1(audio_url, language)
    elif selected_model == AsrModels.usm:
        location = settings.GCP_REGION

        # Create a client
        options = ClientOptions(api_endpoint=f"{location}-speech.googleapis.com")
        client = cloud_speech.SpeechClient(client_options=options)

        # preprocess language into BCP-47 code to avoid generating multiple recognizers for the same languages
        if language:
            lobj = langcodes.Language.get(language.strip())
            assert lobj.is_valid(), f"Invalid language: {language!r}"
            language = lobj.to_tag()
            if language == "en":
                language = "en-US"
            assert language in CHIRP_SUPPORTED, f"Unsupported language: {language!r}"
        else:
            language = None

        recognizer = _get_or_create_recognizer(client, language, location)

        # Initialize request argument(s)
        config = cloud_speech.RecognitionConfig()
        if language:
            config.language_codes = [language]
        else:
            config.language_codes = CHIRP_SUPPORTED  # pick from supported langauges
            config.model = "chirp"  # use chirp model
        config.explicit_decoding_config = cloud_speech.ExplicitDecodingConfig(
            encoding=AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            audio_channel_count=1,
        )
        config.features = cloud_speech.RecognitionFeatures(
            enable_automatic_punctuation=True,
        )
        audio = cloud_speech.BatchRecognizeFileMetadata()
        audio.uri = gs_url_to_uri(audio_url)
        # Specify that results should be inlined in the response (only possible for 1 audio file)
        output_config = cloud_speech.RecognitionOutputConfig()
        output_config.inline_response_config = cloud_speech.InlineOutputConfig()
        request = cloud_speech.BatchRecognizeRequest(
            recognizer=recognizer,
            config=config,
            files=[audio],
            recognition_output_config=output_config,
        )

        # Make the request
        operation = client.batch_recognize(request=request)
        # Wait for operation to complete
        response = operation.result()  # BatchRecognizeFileResult
        # Handle the response
        return "\n\n".join(
            result.alternatives[0].transcript
            for batch in response.results.values()  # BatchRecognizeResults
            for result in batch.transcript.results  # SpeechRecognitionResult
            if result.alternatives
        )
    elif selected_model == AsrModels.mbaza_ctc_large:
        data = call_celery_task(
            "nemo_asr",
            pipeline=dict(
                model_id=asr_model_ids[selected_model],
            ),
            inputs=dict(
                audio=audio_url,
            ),
        )
    elif selected_model == AsrModels.mms_1b_all:
        data = call_celery_task(
            "mms",
            pipeline=dict(
                model_id=asr_model_ids[selected_model],
            ),
            inputs=dict(
                audio=audio_url,
                return_timestamps=output_format != AsrOutputFormat.text,
                language=language,
            ),
            # queue_prefix="gooey-gpu/short" if is_short else "gooey-gpu/long",
        )
    elif selected_model == AsrModels.ghana_nlp_asr_v2:
        audio_r = requests.get(audio_url)
        raise_for_status(audio_r, is_user_url=True)
        r = requests.post(
            furl(
                "https://translation-api.ghananlp.org/asr/v2/transcribe",
                query_params=dict(language=language),
            ),
            headers={
                "Content-Type": "audio/wav",
                "Cache-Control": "no-cache",
                **GHANA_API_AUTH_HEADERS,
            },
            data=audio_r.content,
        )
        raise_for_status(r)
        data = r.json()
    elif selected_model == AsrModels.lelapa:
        audio_r = requests.get(audio_url)
        params = language and {"lang_code": language} or None
        r = requests.post(
            "https://vulavula-services.lelapa.ai/api/v2alpha/transcribe/sync/file",
            headers={"X-CLIENT-TOKEN": settings.LELAPA_API_KEY},
            files={"file": audio_r.content},
            params=params,
        )
        raise_for_status(r)

        return r.json()["transcription_text"]
    elif selected_model == AsrModels.meta_omnilingual_asr_llm_7b:
        import modal
        from modal_functions.meta_omnilingual_asr import app as modal_app

        # Ensure language is in the correct format (e.g., "eng_Latn")
        if language and language not in OMNILINGUAL_ASR_SUPPORTED:
            raise UserError(f"Unsupported language: {language}")

        Omnilingual = modal.Cls.from_name(modal_app.name, "Omnilingual")
        with modal.enable_output():
            transcription = Omnilingual().run.remote(
                audio_url=audio_url, language=language
            )
        return transcription
    elif selected_model in {AsrModels.gpt_4_o_audio, AsrModels.gpt_4_o_mini_audio}:
        from daras_ai_v2.language_model import get_openai_client

        audio_r = requests.get(audio_url)
        raise_for_status(audio_r, is_user_url=True)

        model_id = asr_model_ids[selected_model]
        client = get_openai_client(model_id)
        return client.audio.transcriptions.create(
            model=model_id,
            file=(audio_url, audio_r.content),
            prompt=input_prompt,
            response_format="text",
        )
    # call one of the self-hosted models
    else:
        kwargs = {"task": "translate" if speech_translation_target else "transcribe"}
        if "vakyansh" in selected_model.name:
            # fixes https://github.com/huggingface/transformers/issues/15275#issuecomment-1624879632
            kwargs["decoder_kwargs"] = dict(skip_special_tokens=True)
            kwargs["chunk_length_s"] = 60
            kwargs["stride_length_s"] = (6, 0)
            kwargs["batch_size"] = 32
        elif selected_model == AsrModels.whisper_akera_large_v3:
            # don't pass language or task
            kwargs.pop("task", None)
            kwargs["max_length"] = 448
        elif selected_model == AsrModels.whisper_sunbird_large_v3 and language:
            kwargs["language"] = SUNBIRD_SUPPORTED_LANGUAGES[language.strip()]
        elif "whisper" in selected_model.name:
            forced_lang = forced_asr_languages.get(selected_model)
            if forced_lang:
                kwargs["language"] = forced_lang
            elif language:
                lobj = langcodes.Language.get(language.strip())
                assert lobj.is_valid(), f"Invalid language: {language!r}"
                kwargs["language"] = lobj.language
        data = call_celery_task(
            "whisper",
            pipeline=dict(
                model_id=asr_model_ids[selected_model],
            ),
            inputs=dict(
                audio=audio_url,
                return_timestamps=output_format != AsrOutputFormat.text,
                **kwargs,
            ),
            queue_prefix="gooey-gpu/short" if is_short else "gooey-gpu/long",
        )
    match output_format:
        case AsrOutputFormat.text:
            return data["text"].strip()
        case AsrOutputFormat.json:
            return data
        case AsrOutputFormat.srt:
            assert data.get("chunks"), f"{selected_model.value} can't generate SRT"
            return generate_srt(data["chunks"])
        case AsrOutputFormat.vtt:
            assert data.get("chunks"), f"{selected_model.value} can't generate VTT"
            return generate_vtt(data["chunks"])
        case _:
            raise UserError(f"Invalid output format: {output_format}")


def _get_or_create_recognizer(
    client: "google.cloud.speech_v2.SpeechClient", language: str | None, location: str
) -> str:
    import google.api_core.exceptions
    import google.cloud.speech_v2 as cloud_speech

    _, project = get_google_auth_session()
    if language:
        recognizer_id = f"chirp-api--{language.lower()}"
        try:
            # check if recognizer already exists
            recognizer = client.get_recognizer(
                name=f"projects/{project}/locations/{location}/recognizers/{recognizer_id}"
            ).name
        except google.api_core.exceptions.NotFound:
            # create recognizer if it doesn't exist
            recognizer = (
                client.create_recognizer(
                    parent=f"projects/{project}/locations/{location}",
                    recognizer_id=recognizer_id,
                    recognizer=cloud_speech.Recognizer(
                        language_codes=[language], model="chirp"
                    ),
                )
                .result()
                .name
            )
    else:
        # no language provided => use default implicit recognizer
        recognizer = f"projects/{project}/locations/{location}/recognizers/_"
    return recognizer


# 16kHz, 16-bit, mono
FFMPEG_WAV_ARGS = ["-vn", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000"]


def download_youtube_to_wav_url(youtube_url: str) -> tuple[str, int]:
    """
    Convert a youtube video to wav audio file.
    Returns:
        str: url of the wav audio file.
    """
    wavdata = download_youtube_to_wav(youtube_url)
    # upload the wav file
    return upload_file_from_bytes("yt_audio.wav", wavdata, "audio/wav"), len(wavdata)


_yt_dlp_lock = multiprocessing.Semaphore(1)


def download_youtube_to_wav(youtube_url: str) -> bytes:
    with _yt_dlp_lock, tempfile.TemporaryDirectory() as tmpdir:
        infile = os.path.join(tmpdir, "infile")
        outfile = os.path.join(tmpdir, "outfile.wav")
        proxy_args = []
        if proxy := SCRAPING_PROXIES.get("https"):
            proxy_args += ["--proxy", proxy]
        if cert := get_scraping_proxy_cert_path():
            proxy_args += ["--client-certificate-key", cert]
        # run yt-dlp to download audio
        call_cmd(
            "yt-dlp", "-v",
            "--no-playlist",
            "--max-downloads", "1",
            "--format", "bestaudio/best",
            "--output", infile,
            *proxy_args,
            youtube_url,
            # ignore MaxDownloadsReached - https://github.com/ytdl-org/youtube-dl/blob/a452f9437c8a3048f75fc12f75bcfd3eed78430f/youtube_dl/__init__.py#L468
            ok_returncodes={101},
        )  # fmt:skip
        # convert audio to single channel wav
        ffmpeg("-i", infile, *FFMPEG_WAV_ARGS, outfile)
        # read wav file into memory
        with open(outfile, "rb") as f:
            wavdata = f.read()
    return wavdata


def audio_url_to_wav(audio_url: str) -> tuple[bytes, int]:
    from daras_ai_v2.vector_search import is_yt_dlp_able_url

    if is_yt_dlp_able_url(audio_url):
        wavdata = download_youtube_to_wav(audio_url)
        return wavdata, len(wavdata)

    if is_gdrive_url(furl(audio_url)):
        meta: dict[str, str] = gdrive_metadata(url_to_gdrive_file_id(furl(audio_url)))
        anybytes, _ = gdrive_download(
            furl(audio_url), meta.get("mimeType", "audio/wav")
        )
        return audio_bytes_to_wav(anybytes)

    r = requests.get(audio_url)
    raise_for_status(r, is_user_url=True)
    return audio_bytes_to_wav(r.content)


def audio_url_to_wav_url(audio_url: str) -> tuple[str, int]:
    from daras_ai_v2.vector_search import is_yt_dlp_able_url

    if is_gdrive_url(furl(audio_url)):
        meta: dict[str, str] = gdrive_metadata(url_to_gdrive_file_id(furl(audio_url)))
        anybytes, _ = gdrive_download(
            furl(audio_url), meta.get("mimeType", "audio/wav")
        )
        wavbytes, size = audio_bytes_to_wav(anybytes)
        audio_url = upload_file_from_bytes(
            filename=meta.get("name", "gdrive_audio") + ".wav",
            data=wavbytes,
            content_type="audio/wav",
        )
        return audio_url, size

    if is_yt_dlp_able_url(audio_url):
        return download_youtube_to_wav_url(audio_url)

    r = requests.get(audio_url)
    raise_for_status(r, is_user_url=True)
    audio_bytes = r.content
    wavdata, size = audio_bytes_to_wav(audio_bytes)
    if wavdata is audio_bytes:  # no change, don't re-upload
        return audio_url, size
    else:
        filename = furl(audio_url.strip("/")).path.segments[-1] + ".wav"
        return upload_file_from_bytes(filename, wavdata, "audio/wav"), len(wavdata)


def audio_bytes_to_wav(audio_bytes: bytes) -> tuple[bytes, int]:
    with tempfile.NamedTemporaryFile() as infile:
        infile.write(audio_bytes)
        infile.flush()

        if check_wav_audio_format(infile.name):
            # already a wav file
            return audio_bytes, os.path.getsize(infile.name)

        with tempfile.NamedTemporaryFile(suffix=".wav") as outfile:
            # convert audio to single channel wav
            ffmpeg("-i", infile.name, *FFMPEG_WAV_ARGS, outfile.name)
            return outfile.read(), os.path.getsize(outfile.name)


def check_wav_audio_format(filename: str) -> bool:
    data = ffprobe(filename)
    return (
        len(data["streams"]) == 1
        and data["streams"][0]["codec_name"] == "pcm_s16le"
        and data["streams"][0]["channels"] == 1
        and data["streams"][0]["sample_rate"] == "16000"
    )


# code stolen from https://github.com/openai/whisper/blob/248b6cb124225dd263bb9bd32d060b6517e067f8/whisper/utils.py#L239
#


def generate_vtt(chunks: list[AsrChunk]):
    vtt = "WEBVTT\n"
    subs = iterate_subtitles(chunks, always_include_hours=False, decimal_marker=".")
    for start, end, text in subs:
        vtt += f"{start} --> {end}\n{text}\n\n"
    return vtt


def generate_srt(chunks: list[AsrChunk]):
    srt = ""
    subs = iterate_subtitles(chunks, always_include_hours=True, decimal_marker=",")
    for i, (start, end, text) in enumerate(subs, start=1):
        srt += f"{i}\n{start} --> {end}\n{text}\n\n"
    return srt


def iterate_subtitles(
    chunks: list[AsrChunk], always_include_hours: bool, decimal_marker: str
):
    for chunk in chunks:
        segment_start = format_timestamp(
            chunk["timestamp"][0], always_include_hours, decimal_marker
        )
        segment_end = format_timestamp(
            chunk["timestamp"][1], always_include_hours, decimal_marker
        )
        segment_text = chunk["text"].strip().replace("-->", "->")
        yield segment_start, segment_end, segment_text


INFINITY_SECONDS = 99 * 3600 + 59 * 60 + 59  # 99:59:59 in seconds


def format_timestamp(
    seconds: float | None, always_include_hours: bool, decimal_marker: str
):
    if seconds is None:
        # treat None as end of time
        seconds = INFINITY_SECONDS
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)

    hours = milliseconds // 3_600_000
    milliseconds -= hours * 3_600_000

    minutes = milliseconds // 60_000
    milliseconds -= minutes * 60_000

    seconds = milliseconds // 1_000
    milliseconds -= seconds * 1_000

    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
    return (
        f"{hours_marker}{minutes:02d}:{seconds:02d}{decimal_marker}{milliseconds:03d}"
    )


def should_translate_lang(tag: str) -> bool:
    return tag and tag.split("-")[0] not in {"en", "eng"}
