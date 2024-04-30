import multiprocessing
import os.path
import os.path
import tempfile
import typing
from enum import Enum

import requests
import typing_extensions
from django.db.models import F
from furl import furl

import gooey_gui as gui
from daras_ai.image_input import upload_file_from_bytes, gs_url_to_uri
from daras_ai_v2 import settings
from daras_ai_v2.azure_asr import azure_asr
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
from daras_ai_v2.redis_cache import redis_cache_decorator
from daras_ai_v2.text_splitter import text_splitter

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
    "af-ZA", "sq-AL", "am-ET", "ar-EG", "hy-AM", "as-IN", "ast-ES", "az-AZ", "eu-ES", "be-BY", "bs-BA", "bg-BG",
    "my-MM", "ca-ES", "ceb-PH", "ckb-IQ", "yue-Hant-HK", "zh-TW", "hr-HR", "cs-CZ", "da-DK", "nl-NL",
    "en-AU", "en-IN", "en-GB", "en-US", "et-EE", "fil-PH", "fi-FI", "fr-CA", "fr-FR", "gl-ES", "ka-GE", "de-DE",
    "el-GR", "gu-IN", "ha-NG", "iw-IL", "hi-IN", "hu-HU", "is-IS", "id-ID", "it-IT", "ja-JP", "jv-ID", "kea-CV",
    "kam-KE", "kn-IN", "kk-KZ", "km-KH", "ko-KR", "ky-KG", "lo-LA", "lv-LV", "ln-CD", "lt-LT", "luo-KE", "lb-LU",
    "mk-MK", "ms-MY", "ml-IN", "mt-MT", "mi-NZ", "mr-IN", "mn-MN", "ne-NP", "no-NO", "ny-MW", "oc-FR", "ps-AF", "fa-IR",
    "pl-PL", "pt-BR", "pa-Guru-IN", "ro-RO", "ru-RU", "nso-ZA", "sr-RS", "sn-ZW", "sd-IN", "si-LK", "sk-SK", "sl-SI",
    "so-SO", "es-ES", "es-US", "su-ID", "sw", "sv-SE", "tg-TJ", "ta-IN", "te-IN", "th-TH", "tr-TR", "uk-UA", "ur-PK",
    "uz-UZ", "vi-VN", "cy-GB", "wo-SN", "yo-NG", "zu-ZA"
}  # fmt: skip

WHISPER_SUPPORTED = {
    "af", "ar", "hy", "az", "be", "bs", "bg", "ca", "zh", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "gl", "de",
    "el", "he", "hi", "hu", "is", "id", "it", "ja", "kn", "kk", "ko", "lv", "lt", "mk", "ms", "mr", "mi", "ne", "no",
    "fa", "pl", "pt", "ro", "ru", "sr", "sk", "sl", "es", "sw", "sv", "tl", "ta", "th", "tr", "uk", "ur", "vi", "cy"
}  # fmt: skip

# See page 14 of https://scontent-sea1-1.xx.fbcdn.net/v/t39.2365-6/369747868_602316515432698_2401716319310287708_n.pdf?_nc_cat=106&ccb=1-7&_nc_sid=3c67a6&_nc_ohc=_5cpNOcftdYAX8rCrVo&_nc_ht=scontent-sea1-1.xx&oh=00_AfDVkx7XubifELxmB_Un-yEYMJavBHFzPnvTbTlalbd_1Q&oe=65141B39
# For now, below are listed the languages that support ASR. Note that Seamless only accepts ISO 639-3 codes.
SEAMLESS_SUPPORTED = {
    "afr", "amh", "arb", "ary", "arz", "asm", "ast", "azj", "bel", "ben", "bos", "bul", "cat", "ceb", "ces", "ckb",
    "cmn", "cym", "dan", "deu", "ell", "eng", "est", "eus", "fin", "fra", "gaz", "gle", "glg", "guj", "heb", "hin",
    "hrv", "hun", "hye", "ibo", "ind", "isl", "ita", "jav", "jpn", "kam", "kan", "kat", "kaz", "kea", "khk", "khm",
    "kir", "kor", "lao", "lit", "ltz", "lug", "luo", "lvs", "mai", "mal", "mar", "mkd", "mlt", "mni", "mya", "nld",
    "nno", "nob", "npi", "nya", "oci", "ory", "pan", "pbt", "pes", "pol", "por", "ron", "rus", "slk", "slv", "sna",
    "snd", "som", "spa", "srp", "swe", "swh", "tam", "tel", "tgk", "tgl", "tha", "tur", "ukr", "urd", "uzn", "vie",
    "xho", "yor", "yue", "zlm", "zul"
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

# https://translation.ghananlp.org/api-details#api=ghananlp-translation-webservice-api
GHANA_NLP_SUPPORTED = { 'en': 'English', 'tw': 'Twi', 'gaa': 'Ga', 'ee': 'Ewe', 'fat': 'Fante', 'dag': 'Dagbani', 'gur': 'Gurene', 'yo': 'Yoruba', 'ki': 'Kikuyu', 'luo': 'Luo', 'mer': 'Kimeru' }  # fmt: skip
GHANA_NLP_MAXLEN = 500


class AsrModels(Enum):
    whisper_large_v2 = "Whisper Large v2 (openai)"
    whisper_large_v3 = "Whisper Large v3 (openai)"
    whisper_hindi_large_v2 = "Whisper Hindi Large v2 (Bhashini)"
    whisper_telugu_large_v2 = "Whisper Telugu Large v2 (Bhashini)"
    nemo_english = "Conformer English (ai4bharat.org)"
    nemo_hindi = "Conformer Hindi (ai4bharat.org)"
    vakyansh_bhojpuri = "Vakyansh Bhojpuri (Open-Speech-EkStep)"
    gcp_v1 = "Google Cloud V1"
    usm = "Chirp / USM (Google V2)"
    deepgram = "Deepgram"
    azure = "Azure Speech"
    seamless_m4t = "Seamless M4T (Facebook Research)"
    mms_1b_all = "Massively Multilingual Speech (MMS) (Facebook Research)"

    def supports_auto_detect(self) -> bool:
        return self not in {self.azure, self.gcp_v1, self.mms_1b_all}


asr_model_ids = {
    AsrModels.whisper_large_v3: "vaibhavs10/incredibly-fast-whisper:37dfc0d6a7eb43ff84e230f74a24dab84e6bb7756c9b457dbdcceca3de7a4a04",
    AsrModels.whisper_large_v2: "openai/whisper-large-v2",
    AsrModels.whisper_hindi_large_v2: "vasista22/whisper-hindi-large-v2",
    AsrModels.whisper_telugu_large_v2: "vasista22/whisper-telugu-large-v2",
    AsrModels.vakyansh_bhojpuri: "Harveenchadha/vakyansh-wav2vec2-bhojpuri-bhom-60",
    AsrModels.nemo_english: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/english_large_data_fixed.nemo",
    AsrModels.nemo_hindi: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/stt_hi_conformer_ctc_large_v2.nemo",
    AsrModels.seamless_m4t: "facebook/seamless-m4t-v2-large",
    AsrModels.mms_1b_all: "facebook/mms-1b-all",
}

forced_asr_languages = {
    AsrModels.whisper_hindi_large_v2: "hi",
    AsrModels.whisper_telugu_large_v2: "te",
    AsrModels.vakyansh_bhojpuri: "bho",
    AsrModels.nemo_english: "en",
    AsrModels.nemo_hindi: "hi",
}

asr_supported_languages = {
    AsrModels.whisper_large_v3: WHISPER_SUPPORTED,
    AsrModels.whisper_large_v2: WHISPER_SUPPORTED,
    AsrModels.gcp_v1: GCP_V1_SUPPORTED,
    AsrModels.usm: CHIRP_SUPPORTED,
    AsrModels.deepgram: DEEPGRAM_SUPPORTED,
    AsrModels.seamless_m4t: SEAMLESS_SUPPORTED,
    AsrModels.azure: AZURE_SUPPORTED,
    AsrModels.mms_1b_all: MMS_SUPPORTED,
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


class TranslationModels(TranslationModel, Enum):
    google = TranslationModel(
        label="Google Translate",
        supports_glossary=True,
        supports_auto_detect=True,
    )
    ghana_nlp = TranslationModel(
        label="Ghana NLP Translate",
    )


def translation_language_selector(
    *,
    model: TranslationModels | None,
    label: str,
    key: str,
    **kwargs,
) -> str | None:
    if not model:
        gui.session_state[key] = None
        return

    if model == TranslationModels.google:
        languages = google_translate_target_languages()
    elif model == TranslationModels.ghana_nlp:
        languages = GHANA_NLP_SUPPORTED
    else:
        raise ValueError("Unsupported translation model: " + str(model))

    options = list(languages.keys())
    return gui.selectbox(
        label=label,
        key=key,
        format_func=lang_format_func,
        options=options,
        **kwargs,
    )


def translation_model_selector(
    key="translation_model", allow_none=True
) -> TranslationModels | None:
    from daras_ai_v2.enum_selector_widget import enum_selector

    model = enum_selector(
        TranslationModels,
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
def google_translate_target_languages() -> dict[str, str]:
    """
    Get list of supported languages for Google Translate.
    :return: Dictionary of language codes and display names.
    """
    from google.cloud import translate

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
    from google.cloud import translate

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


def asr_language_selector(
    selected_model: AsrModels,
    label="##### Spoken Language",
    key="language",
):
    # don't show language selector for models with forced language
    forced_lang = forced_asr_languages.get(selected_model)
    if forced_lang:
        gui.session_state[key] = forced_lang
        return forced_lang

    options = list(asr_supported_languages.get(selected_model, []))
    if selected_model and selected_model.supports_auto_detect():
        options.insert(0, None)

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
    )


def lang_format_func(l):
    import langcodes

    if not l:
        return "Auto Detect"
    try:
        return f"{langcodes.Language.get(l).display_name()} | {l}"
    except langcodes.LanguageTagError:
        return l


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
    else:
        raise ValueError("Unsupported translation model: " + str(model))


def run_ghana_nlp_translate(
    texts: list[str],
    target_language: str,
    source_language: str,
) -> list[str]:
    assert (
        source_language and target_language
    ), "Both Source & Target language is required for Ghana NLP"
    source_language = normalised_lang_in_collection(
        source_language, GHANA_NLP_SUPPORTED
    )
    target_language = normalised_lang_in_collection(
        target_language, GHANA_NLP_SUPPORTED
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
        headers={"Ocp-Apim-Subscription-Key": str(settings.GHANA_NLP_SUBKEY)},
        json={"in": text, "lang": source_language + "-" + target_language},
    )
    raise_for_status(r)
    return r.json()


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


def normalised_lang_in_collection(target: str, collection: typing.Iterable[str]) -> str:
    import langcodes

    ERROR = UserError(
        f"Unsupported language: {target!r} | must be one of {set(collection)}"
    )

    if target in collection:
        return target

    try:
        target_lan = langcodes.Language.get(target).language
    except langcodes.LanguageTagError:
        raise ERROR

    for candidate in collection:
        try:
            if candidate and langcodes.Language.get(candidate).language == target_lan:
                return candidate
        except langcodes.LanguageTagError:
            pass

    raise ERROR


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


_session = None


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


def get_google_auth_session():
    global _session

    if _session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        # takes care of refreshing the token and adding it to request headers
        _session = AuthorizedSession(credentials=creds), project

    return _session


def run_asr(
    audio_url: str,
    selected_model: str,
    language: str = None,
    output_format: str = "text",
) -> str | AsrOutputJson:
    """
    Run ASR on audio.
    Args:
        audio_url (str): url of audio to be transcribed.
        selected_model (str): ASR model to use.
        language: language of the audio
        output_format: format of the output
    Returns:
        str: Transcribed text.
    """
    import google.cloud.speech_v2 as cloud_speech
    from google.api_core.client_options import ClientOptions
    from google.cloud.texttospeech_v1 import AudioEncoding
    from daras_ai_v2.vector_search import is_yt_url
    import langcodes

    selected_model = AsrModels[selected_model]
    output_format = AsrOutputFormat[output_format]
    if is_yt_url(audio_url):
        audio_url, size = download_youtube_to_wav_url(audio_url)
    elif is_gdrive_url(furl(audio_url)):
        meta: dict[str, str] = gdrive_metadata(url_to_gdrive_file_id(furl(audio_url)))
        anybytes, _ = gdrive_download(
            furl(audio_url), meta.get("mimeType", "audio/wav")
        )
        wavbytes, size = audio_bytes_to_wav(anybytes)
        audio_url = upload_file_from_bytes(
            filename=meta.get("name", "gdrive_audio"),
            data=wavbytes,
            content_type=meta.get("mimeType", "audio/wav"),
        )
    else:
        audio_url, size = audio_url_to_wav(audio_url)
    is_short = size < SHORT_FILE_CUTOFF

    if selected_model == AsrModels.azure:
        return azure_asr(audio_url, language)
    elif selected_model == AsrModels.whisper_large_v3:
        import replicate

        config = {
            "audio": audio_url,
            "return_timestamps": output_format != AsrOutputFormat.text,
        }
        if language:
            config["language"] = language
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
    elif selected_model == AsrModels.seamless_m4t:
        data = call_celery_task(
            "seamless",
            pipeline=dict(
                model_id=asr_model_ids[AsrModels.seamless_m4t],
            ),
            inputs=dict(
                audio=audio_url,
                task="ASR",
                src_lang=language,
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
    elif "nemo" in selected_model.name:
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
    # call one of the self-hosted models
    else:
        kwargs = {}
        if "vakyansh" in selected_model.name:
            # fixes https://github.com/huggingface/transformers/issues/15275#issuecomment-1624879632
            kwargs["decoder_kwargs"] = dict(skip_special_tokens=True)
            kwargs["chunk_length_s"] = 60
            kwargs["stride_length_s"] = (6, 0)
            kwargs["batch_size"] = 32
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
                task="transcribe",
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
        # run yt-dlp to download audio
        call_cmd(
            "yt-dlp",
            "--no-playlist",
            "--max-downloads", "1",
            "--format", "bestaudio",
            "--output", infile,
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


def audio_url_to_wav(audio_url: str) -> tuple[str, int]:
    r = requests.get(audio_url)
    try:
        raise_for_status(r, is_user_url=True)
    except requests.HTTPError:
        # wait 3 seconds and try again (handles cases where the url has just been uploaded but cache is not updated yet, e.g. for Twilio)
        from time import sleep

        sleep(3)
        r = requests.get(audio_url)
        raise_for_status(r, is_user_url=True)

    wavdata, size = audio_bytes_to_wav(r.content)
    if not wavdata:
        return audio_url, size

    filename = furl(audio_url.strip("/")).path.segments[-1] + ".wav"
    return upload_file_from_bytes(filename, wavdata, "audio/wav"), len(wavdata)


def audio_bytes_to_wav(audio_bytes: bytes) -> tuple[bytes | None, int]:
    with tempfile.NamedTemporaryFile() as infile:
        infile.write(audio_bytes)
        infile.flush()

        if check_wav_audio_format(infile.name):
            # already a wav file
            return None, os.path.getsize(infile.name)

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


def should_translate_lang(code: str) -> bool:
    return code and code.split("-")[0] != "en"
