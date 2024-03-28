import os.path
import os.path
import tempfile
from enum import Enum

import requests
import typing_extensions
from django.db.models import F
from furl import furl

import gooey_ui as st
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

TRANSLATE_DETECT_BATCH_SIZE = 8

SHORT_FILE_CUTOFF = 5 * 1024 * 1024  # 1 MB

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

MMS_SUPPORTED = ['abi (Abidji\n)', 'abk (Abkhaz\n)', 'abp (Ayta, Abellen\n)', 'aca (Achagua\n)', 'acd (Gikyode\n)', 'ace (Aceh\n)', 'acf (Lesser Antillean French Creole\n)', 'ach (Acholi\n)', 'acn (Achang\n)', 'acr (Achi\n)', 'acu (Achuar-Shiwiar\n)', 'ade (Adele\n)', 'adh (Jopadhola\n)', 'adj (Adioukrou\n)', 'adx (Tibetan, Amdo\n)', 'aeu (Akeu\n)', 'afr (Afrikaans\n)', 'agd (Agarabi\n)', 'agg (Angor\n)', 'agn (Agutaynen\n)', 'agr (Awajún\n)', 'agu (Awakateko\n)', 'agx (Aghul\n)', 'aha (Ahanta\n)', 'ahk (Akha\n)', 'aia (Arosi\n)', 'aka (Akan\n)', 'akb (Batak Angkola\n)', 'ake (Akawaio\n)', 'akp (Siwu\n)', 'alj (Alangan\n)', 'alp (Alune\n)', 'alt (Altai, Southern\n)', 'alz (Alur\n)', 'ame (Yanesha’\n)', 'amf (Hamer-Banna\n)', 'amh (Amharic\n)', 'ami (Amis\n)', 'amk (Ambai\n)', 'ann (Obolo\n)', 'any (Anyin\n)', 'aoz (Uab Meto\n)', 'apb (Sa’a\n)', 'apr (Arop-Lokep\n)', 'ara (Arabic\n)', 'arl (Arabela\n)', 'asa (Asu\n)', 'asg (Cishingini\n)', 'asm (Assamese\n)', 'ast (Asturian\n)', 'ata (Pele-Ata\n)', 'atb (Zaiwa\n)', 'atg (Ivbie North-Okpela-Arhe\n)', 'ati (Attié\n)', 'atq (Aralle-Tabulahan\n)', 'ava (Avar\n)', 'avn (Avatime\n)', 'avu (Avokaya\n)', 'awa (Awadhi\n)', 'awb (Awa\n)', 'ayo (Ayoreo\n)', 'ayr (Aymara, Central\n)', 'ayz (Mai Brat\n)', 'azb (Azerbaijani, South\n)', 'azg (Amuzgo, San Pedro Amuzgos\n)', 'azj-script_cyrillic (Azerbaijani, North\n)', 'azj-script_latin (Azerbaijani, North\n)', 'azz (Nahuatl, Highland Puebla\n)', 'bak (Bashkort\n)', 'bam (Bamanankan\n)', 'ban (Bali\n)', 'bao (Waimaha\n)', 'bas (Basaa\n)', 'bav (Vengo\n)', 'bba (Baatonum\n)', 'bbb (Barai\n)', 'bbc (Batak Toba\n)', 'bbo (Konabéré\n)', 'bcc-script_arabic (Balochi, Southern\n)', 'bcc-script_latin (Balochi, Southern\n)', 'bcl (Bikol, Central\n)', 'bcw (Bana\n)', 'bdg (Bonggi\n)', 'bdh (Baka\n)', 'bdq (Bahnar\n)', 'bdu (Oroko\n)', 'bdv (Bodo Parja\n)', 'beh (Biali\n)', 'bel (Belarusian\n)', 'bem (Bemba\n)', 'ben (Bengali\n)', 'bep (Behoa\n)', 'bex (Jur Modo\n)', 'bfa (Bari\n)', 'bfo (Birifor, Malba\n)', 'bfy (Bagheli\n)', 'bfz (Pahari, Mahasu\n)', 'bgc (Haryanvi\n)', 'bgq (Bagri\n)', 'bgr (Chin, Bawm\n)', 'bgt (Bughotu\n)', 'bgw (Bhatri\n)', 'bha (Bharia\n)', 'bht (Bhattiyali\n)', 'bhz (Bada\n)', 'bib (Bisa\n)', 'bim (Bimoba\n)', 'bis (Bislama\n)', 'biv (Birifor, Southern\n)', 'bjr (Binumarien\n)', 'bjv (Bedjond\n)', 'bjw (Bakwé\n)', 'bjz (Baruga\n)', 'bkd (Binukid\n)', 'bkv (Bekwarra\n)', 'blh (Kuwaa\n)', 'blt (Tai Dam\n)', 'blx (Ayta, Mag-Indi\n)', 'blz (Balantak\n)', 'bmq (Bomu\n)', 'bmr (Muinane\n)', 'bmu (Somba-Siawari\n)', 'bmv (Bum\n)', 'bng (Benga\n)', 'bno (Bantoanon\n)', 'bnp (Bola\n)', 'boa (Bora\n)', 'bod (Tibetan, Central\n)', 'boj (Anjam\n)', 'bom (Berom\n)', 'bor (Borôro\n)', 'bos (Bosnian\n)', 'bov (Tuwuli\n)', 'box (Buamu\n)', 'bpr (Blaan, Koronadal\n)', 'bps (Blaan, Sarangani\n)', 'bqc (Boko\n)', 'bqi (Bakhtiâri\n)', 'bqj (Bandial\n)', 'bqp (Bisã\n)', 'bre (Breton\n)', 'bru (Bru, Eastern\n)', 'bsc (Oniyan\n)', 'bsq (Bassa\n)', 'bss (Akoose\n)', 'btd (Batak Dairi\n)', 'bts (Batak Simalungun\n)', 'btt (Bete-Bendi\n)', 'btx (Batak Karo\n)', 'bud (Ntcham\n)', 'bul (Bulgarian\n)', 'bus (Bokobaru\n)', 'bvc (Baelelea\n)', 'bvz (Bauzi\n)', 'bwq (Bobo Madaré, Southern\n)', 'bwu (Buli\n)', 'byr (Yipma\n)', 'bzh (Buang, Mapos\n)', 'bzi (Bisu\n)', 'bzj (Belize English Creole\n)', 'caa (Ch’orti’\n)', 'cab (Garifuna\n)', 'cac-dialect_sanmateoixtatan (Chuj\n)', 'cac-dialect_sansebastiancoatan (Chuj\n)', 'cak-dialect_central (Kaqchikel\n)', 'cak-dialect_santamariadejesus (Kaqchikel\n)', 'cak-dialect_santodomingoxenacoj (Kaqchikel\n)', 'cak-dialect_southcentral (Kaqchikel\n)', 'cak-dialect_western (Kaqchikel\n)', 'cak-dialect_yepocapa (Kaqchikel\n)', 'cap (Chipaya\n)', 'car (Carib\n)', 'cas (Tsimané\n)', 'cat (Catalan\n)', 'cax (Chiquitano\n)', 'cbc (Carapana\n)', 'cbi (Chachi\n)', 'cbr (Kakataibo-Kashibo\n)', 'cbs (Kashinawa\n)', 'cbt (Shawi\n)', 'cbu (Kandozi-Chapra\n)', 'cbv (Cacua\n)', 'cce (Chopi\n)', 'cco (Chinantec, Comaltepec\n)', 'cdj (Churahi\n)', 'ceb (Cebuano\n)', 'ceg (Chamacoco\n)', 'cek (Chin, Eastern Khumi\n)', 'ces (Czech\n)', 'cfm (Chin, Falam\n)', 'cgc (Kagayanen\n)', 'che (Chechen\n)', 'chf (Chontal, Tabasco\n)', 'chv (Chuvash\n)', 'chz (Chinantec, Ozumacín\n)', 'cjo (Ashéninka, Pajonal\n)', 'cjp (Cabécar\n)', 'cjs (Shor\n)', 'ckb (Kurdish, Central\n)', 'cko (Anufo\n)', 'ckt (Chukchi\n)', 'cla (Ron\n)', 'cle (Chinantec, Lealao\n)', 'cly (Chatino, Eastern Highland\n)', 'cme (Cerma\n)', 'cmn-script_simplified (Chinese, Mandarin\n)', 'cmo-script_khmer (Mnong, Central\n)', 'cmo-script_latin (Mnong, Central\n)', 'cmr (Mro-Khimi\n)', 'cnh (Chin, Hakha\n)', 'cni (Asháninka\n)', 'cnl (Chinantec, Lalana\n)', 'cnt (Chinantec, Tepetotutla\n)', 'coe (Koreguaje\n)', 'cof (Tsafiki\n)', 'cok (Cora, Santa Teresa\n)', 'con (Cofán\n)', 'cot (Caquinte\n)', 'cou (Wamey\n)', 'cpa (Chinantec, Palantla\n)', 'cpb (Ashéninka, Ucayali-Yurúa\n)', 'cpu (Ashéninka, Pichis\n)', 'crh (Crimean Tatar\n)', 'crk-script_latin (Cree, Plains\n)', 'crk-script_syllabics (Cree, Plains\n)', 'crn (Cora, El Nayar\n)', 'crq (Chorote, Iyo’wujwa\n)', 'crs (Seychelles French Creole\n)', 'crt (Chorote, Iyojwa’ja\n)', 'csk (Jola-Kasa\n)', 'cso (Chinantec, Sochiapam\n)', 'ctd (Chin, Tedim\n)', 'ctg (Chittagonian\n)', 'cto (Embera Catío\n)', 'ctu (Chol\n)', 'cuc (Chinantec, Usila\n)', 'cui (Cuiba\n)', 'cuk (Kuna, San Blas\n)', 'cul (Kulina\n)', 'cwa (Kabwa\n)', 'cwe (Kwere\n)', 'cwt (Kuwaataay\n)', 'cya (Chatino, Nopala\n)', 'cym (Welsh\n)', 'daa (Dangaléat\n)', 'dah (Gwahatike\n)', 'dan (Danish\n)', 'dar (Dargwa\n)', 'dbj (Ida’an\n)', 'dbq (Daba\n)', 'ddn (Dendi\n)', 'ded (Dedua\n)', 'des (Desano\n)', 'deu (German, Standard\n)', 'dga (Dagaare, Southern\n)', 'dgi (Dagara, Northern\n)', 'dgk (Dagba\n)', 'dgo (Dogri\n)', 'dgr (Tlicho\n)', 'dhi (Dhimal\n)', 'did (Didinga\n)', 'dig (Chidigo\n)', 'dik (Dinka, Southwestern\n)', 'dip (Dinka, Northeastern\n)', 'div (Maldivian\n)', 'djk (Aukan\n)', 'dnj-dialect_blowowest (Dan\n)', 'dnj-dialect_gweetaawueast (Dan\n)', 'dnt (Dani, Mid Grand Valley\n)', 'dnw (Dani, Western\n)', 'dop (Lukpa\n)', 'dos (Dogosé\n)', 'dsh (Daasanach\n)', 'dso (Desiya\n)', 'dtp (Kadazan Dusun\n)', 'dts (Dogon, Toro So\n)', 'dug (Chiduruma\n)', 'dwr (Dawro\n)', 'dyi (Sénoufo, Djimini\n)', 'dyo (Jola-Fonyi\n)', 'dyu (Jula\n)', 'dzo (Dzongkha\n)', 'eip (Lik\n)', 'eka (Ekajuk\n)', 'ell (Greek\n)', 'emp (Emberá, Northern\n)', 'enb (Markweeta\n)', 'eng (English\n)', 'enx (Enxet\n)', 'epo (Esperanto\n)', 'ese (Ese Ejja\n)', 'ess (Yupik, Saint Lawrence Island\n)', 'est (Estonian\n)', 'eus (Basque\n)', 'evn (Evenki\n)', 'ewe (Éwé\n)', 'eza (Ezaa\n)', 'fal (Fali, South\n)', 'fao (Faroese\n)', 'far (Fataleka\n)', 'fas (Persian\n)', 'fij (Fijian\n)', 'fin (Finnish\n)', 'flr (Fuliiru\n)', 'fmu (Muria, Far Western\n)', 'fon (Fon\n)', 'fra (French\n)', 'frd (Fordata\n)', 'fry (Frisian\n)', 'ful (Fulah\n)', 'gag-script_cyrillic (Gagauz\n)', 'gag-script_latin (Gagauz\n)', 'gai (Mbore\n)', 'gam (Kandawo\n)', 'gau (Gadaba, Mudhili\n)', 'gbi (Galela\n)', 'gbk (Gaddi\n)', 'gbm (Garhwali\n)', 'gbo (Grebo, Northern\n)', 'gde (Gude\n)', 'geb (Kire\n)', 'gej (Gen\n)', 'gil (Kiribati\n)', 'gjn (Gonja\n)', 'gkn (Gokana\n)', 'gld (Nanai\n)', 'gle (Irish\n)', 'glg (Galician\n)', 'glk (Gilaki\n)', 'gmv (Gamo\n)', 'gna (Kaansa\n)', 'gnd (Zulgo-Gemzek\n)', 'gng (Ngangam\n)', 'gof-script_latin (Gofa\n)', 'gog (Gogo\n)', 'gor (Gorontalo\n)', 'gqr (Gor\n)', 'grc (Greek, Ancient\n)', 'gri (Ghari\n)', 'grn (Guarani\n)', 'grt (Garo\n)', 'gso (Gbaya, Southwest\n)', 'gub (Guajajára\n)', 'guc (Wayuu\n)', 'gud (Dida, Yocoboué\n)', 'guh (Guahibo\n)', 'guj (Gujarati\n)', 'guk (Gumuz\n)', 'gum (Misak\n)', 'guo (Guayabero\n)', 'guq (Aché\n)', 'guu (Yanomamö\n)', 'gux (Gourmanchéma\n)', 'gvc (Wanano\n)', 'gvl (Gulay\n)', 'gwi (Gwich’in\n)', 'gwr (Gwere\n)', 'gym (Ngäbere\n)', 'gyr (Guarayu\n)', 'had (Hatam\n)', 'hag (Hanga\n)', 'hak (Chinese, Hakka\n)', 'hap (Hupla\n)', 'hat (Haitian Creole\n)', 'hau (Hausa\n)', 'hay (Haya\n)', 'heb (Hebrew\n)', 'heh (Hehe\n)', 'hif (Hindi, Fiji\n)', 'hig (Kamwe\n)', 'hil (Hiligaynon\n)', 'hin (Hindi\n)', 'hlb (Halbi\n)', 'hlt (Chin, Matu\n)', 'hne (Chhattisgarhi\n)', 'hnn (Hanunoo\n)', 'hns (Hindustani, Sarnami\n)', 'hoc (Ho\n)', 'hoy (Holiya\n)', 'hrv (Croatian\n)', 'hsb (Sorbian, Upper\n)', 'hto (Witoto, Minika\n)', 'hub (Wampís\n)', 'hui (Huli\n)', 'hun (Hungarian\n)', 'hus-dialect_centralveracruz (Huastec\n)', 'hus-dialect_westernpotosino (Huastec\n)', 'huu (Witoto, Murui\n)', 'huv (Huave, San Mateo del Mar\n)', 'hvn (Hawu\n)', 'hwc (Hawaii Pidgin\n)', 'hye (Armenian\n)', 'hyw (Armenian, Western\n)', 'iba (Iban\n)', 'ibo (Igbo\n)', 'icr (Islander English Creole\n)', 'idd (Ede Idaca\n)', 'ifa (Ifugao, Amganad\n)', 'ifb (Ifugao, Batad\n)', 'ife (Ifè\n)', 'ifk (Ifugao, Tuwali\n)', 'ifu (Ifugao, Mayoyao\n)', 'ify (Kallahan, Keley-i\n)', 'ign (Ignaciano\n)', 'ikk (Ika\n)', 'ilb (Ila\n)', 'ilo (Ilocano\n)', 'imo (Imbongu\n)', 'ina (Interlingua (International Auxiliary Language Association)\n)', 'inb (Inga\n)', 'ind (Indonesian\n)', 'iou (Tuma-Irumu\n)', 'ipi (Ipili\n)', 'iqw (Ikwo\n)', 'iri (Rigwe\n)', 'irk (Iraqw\n)', 'isl (Icelandic\n)', 'ita (Italian\n)', 'itl (Itelmen\n)', 'itv (Itawit\n)', 'ixl-dialect_sangasparchajul (Ixil\n)', 'ixl-dialect_sanjuancotzal (Ixil\n)', 'ixl-dialect_santamarianebaj (Ixil\n)', 'izr (Izere\n)', 'izz (Izii\n)', 'jac (Jakalteko\n)', 'jam (Jamaican English Creole\n)', 'jav (Javanese\n)', 'jbu (Jukun Takum\n)', 'jen (Dza\n)', 'jic (Tol\n)', 'jiv (Shuar\n)', 'jmc (Machame\n)', 'jmd (Yamdena\n)', 'jpn (Japanese\n)', 'jun (Juang\n)', 'juy (Juray\n)', 'jvn (Javanese, Suriname\n)', 'kaa (Karakalpak\n)', 'kab (Amazigh\n)', 'kac (Jingpho\n)', 'kak (Kalanguya\n)', 'kam (Kamba\n)', 'kan (Kannada\n)', 'kao (Xaasongaxango\n)', 'kaq (Capanahua\n)', 'kat (Georgian\n)', 'kay (Kamayurá\n)', 'kaz (Kazakh\n)', 'kbo (Keliko\n)', 'kbp (Kabiyè\n)', 'kbq (Kamano\n)', 'kbr (Kafa\n)', 'kby (Kanuri, Manga\n)', 'kca (Khanty\n)', 'kcg (Tyap\n)', 'kdc (Kutu\n)', 'kde (Makonde\n)', 'kdh (Tem\n)', 'kdi (Kumam\n)', 'kdj (Ng’akarimojong\n)', 'kdl (Tsikimba\n)', 'kdn (Kunda\n)', 'kdt (Kuay\n)', 'kea (Kabuverdianu\n)', 'kek (Q’eqchi’\n)', 'ken (Kenyang\n)', 'keo (Kakwa\n)', 'ker (Kera\n)', 'key (Kupia\n)', 'kez (Kukele\n)', 'kfb (Kolami, Northwestern\n)', 'kff-script_telugu (Koya\n)', 'kfw (Naga, Kharam\n)', 'kfx (Pahari, Kullu\n)', 'khg (Tibetan, Khams\n)', 'khm (Khmer\n)', 'khq (Songhay, Koyra Chiini\n)', 'kia (Kim\n)', 'kij (Kilivila\n)', 'kik (Gikuyu\n)', 'kin (Kinyarwanda\n)', 'kir (Kyrgyz\n)', 'kjb (Q’anjob’al\n)', 'kje (Kisar\n)', 'kjg (Khmu\n)', 'kjh (Khakas\n)', 'kki (Kagulu\n)', 'kkj (Kako\n)', 'kle (Kulung\n)', 'klu (Klao\n)', 'klv (Maskelynes\n)', 'klw (Tado\n)', 'kma (Konni\n)', 'kmd (Kalinga, Majukayang\n)', 'kml (Kalinga, Tanudan\n)', 'kmr-script_arabic (Kurdish, Northern\n)', 'kmr-script_cyrillic (Kurdish, Northern\n)', 'kmr-script_latin (Kurdish, Northern\n)', 'kmu (Kanite\n)', 'knb (Kalinga, Lubuagan\n)', 'kne (Kankanaey\n)', 'knf (Mankanya\n)', 'knj (Akateko\n)', 'knk (Kuranko\n)', 'kno (Kono\n)', 'kog (Kogi\n)', 'kor (Korean\n)', 'kpq (Korupun-Sela\n)', 'kps (Tehit\n)', 'kpv (Komi-Zyrian\n)', 'kpy (Koryak\n)', 'kpz (Kupsapiiny\n)', 'kqe (Kalagan\n)', 'kqp (Kimré\n)', 'kqr (Kimaragang\n)', 'kqy (Koorete\n)', 'krc (Karachay-Balkar\n)', 'kri (Krio\n)', 'krj (Kinaray-a\n)', 'krl (Karelian\n)', 'krr (Krung\n)', 'krs (Gbaya\n)', 'kru (Kurux\n)', 'ksb (Shambala\n)', 'ksr (Borong\n)', 'kss (Kisi, Southern\n)', 'ktb (Kambaata\n)', 'ktj (Krumen, Plapo\n)', 'kub (Kutep\n)', 'kue (Kuman\n)', 'kum (Kumyk\n)', 'kus (Kusaal\n)', 'kvn (Kuna, Border\n)', 'kvw (Wersing\n)', 'kwd (Kwaio\n)', 'kwf (Kwara’ae\n)', 'kwi (Awa-Cuaiquer\n)', 'kxc (Konso\n)', 'kxf (Kawyaw\n)', 'kxm (Khmer, Northern\n)', 'kxv (Kuvi\n)', 'kyb (Kalinga, Butbut\n)', 'kyc (Kyaka\n)', 'kyf (Kouya\n)', 'kyg (Keyagana\n)', 'kyo (Klon\n)', 'kyq (Kenga\n)', 'kyu (Kayah, Western\n)', 'kyz (Kayabí\n)', 'kzf (Kaili, Da’a\n)', 'lac (Lacandon\n)', 'laj (Lango\n)', 'lam (Lamba\n)', 'lao (Lao\n)', 'las (Lama\n)', 'lat (Latin\n)', 'lav (Latvian\n)', 'law (Lauje\n)', 'lbj (Ladakhi\n)', 'lbw (Tolaki\n)', 'lcp (Lawa, Western\n)', 'lee (Lyélé\n)', 'lef (Lelemi\n)', 'lem (Nomaande\n)', 'lew (Kaili, Ledo\n)', 'lex (Luang\n)', 'lgg (Lugbara\n)', 'lgl (Wala\n)', 'lhu (Lahu\n)', 'lia (Limba, West-Central\n)', 'lid (Nyindrou\n)', 'lif (Limbu\n)', 'lin (Lingala\n)', 'lip (Sekpele\n)', 'lis (Lisu\n)', 'lit (Lithuanian\n)', 'lje (Rampi\n)', 'ljp (Lampung Api\n)', 'llg (Lole\n)', 'lln (Lele\n)', 'lme (Pévé\n)', 'lnd (Lundayeh\n)', 'lns (Lamnso’\n)', 'lob (Lobi\n)', 'lok (Loko\n)', 'lom (Loma\n)', 'lon (Lomwe, Malawi\n)', 'loq (Lobala\n)', 'lsi (Lacid\n)', 'lsm (Saamya-Gwe\n)', 'ltz (Luxembourgish\n)', 'luc (Aringa\n)', 'lug (Ganda\n)', 'luo (Dholuo\n)', 'lwo (Luwo\n)', 'lww (Lewo\n)', 'lzz (Laz\n)', 'maa-dialect_sanantonio (Mazatec, San Jerónimo Tecóatl\n)', 'maa-dialect_sanjeronimo (Mazatec, San Jerónimo Tecóatl\n)', 'mad (Madura\n)', 'mag (Magahi\n)', 'mah (Marshallese\n)', 'mai (Maithili\n)', 'maj (Mazatec, Jalapa de Díaz\n)', 'mak (Makasar\n)', 'mal (Malayalam\n)', 'mam-dialect_central (Mam\n)', 'mam-dialect_northern (Mam\n)', 'mam-dialect_southern (Mam\n)', 'mam-dialect_western (Mam\n)', 'maq (Mazatec, Chiquihuitlán\n)', 'mar (Marathi\n)', 'maw (Mampruli\n)', 'maz (Mazahua, Central\n)', 'mbb (Manobo, Western Bukidnon\n)', 'mbc (Macushi\n)', 'mbh (Mangseng\n)', 'mbj (Nadëb\n)', 'mbt (Manobo, Matigsalug\n)', 'mbu (Mbula-Bwazza\n)', 'mbz (Mixtec, Amoltepec\n)', 'mca (Maka\n)', 'mcb (Matsigenka\n)', 'mcd (Sharanahua\n)', 'mco (Mixe, Coatlán\n)', 'mcp (Makaa\n)', 'mcq (Ese\n)', 'mcu (Mambila, Cameroon\n)', 'mda (Mada\n)', 'mdf (Moksha\n)', 'mdv (Mixtec, Santa Lucía Monteverde\n)', 'mdy (Male\n)', 'med (Melpa\n)', 'mee (Mengen\n)', 'mej (Meyah\n)', 'men (Mende\n)', 'meq (Merey\n)', 'met (Mato\n)', 'mev (Maan\n)', 'mfe (Morisyen\n)', 'mfh (Matal\n)', 'mfi (Wandala\n)', 'mfk (Mofu, North\n)', 'mfq (Moba\n)', 'mfy (Mayo\n)', 'mfz (Mabaan\n)', 'mgd (Moru\n)', 'mge (Mango\n)', 'mgh (Makhuwa-Meetto\n)', 'mgo (Meta’\n)', 'mhi (Ma’di\n)', 'mhr (Mari, Meadow\n)', 'mhu (Digaro-Mishmi\n)', 'mhx (Lhao Vo\n)', 'mhy (Ma’anyan\n)', 'mib (Mixtec, Atatlahuca\n)', 'mie (Mixtec, Ocotepec\n)', 'mif (Mofu-Gudur\n)', 'mih (Mixtec, Chayuco\n)', 'mil (Mixtec, Peñoles\n)', 'mim (Mixtec, Alacatlatzala\n)', 'min (Minangkabau\n)', 'mio (Mixtec, Pinotepa Nacional\n)', 'mip (Mixtec, Apasco-Apoala\n)', 'miq (Mískito\n)', 'mit (Mixtec, Southern Puebla\n)', 'miy (Mixtec, Ayutla\n)', 'miz (Mixtec, Coatzospan\n)', 'mjl (Mandeali\n)', 'mjv (Mannan\n)', 'mkd (Macedonian\n)', 'mkl (Mokole\n)', 'mkn (Malay, Kupang\n)', 'mlg (Malagasy\n)', 'mlt (Maltese\n)', 'mmg (Ambrym, North\n)', 'mnb (Muna\n)', 'mnf (Mundani\n)', 'mnk (Mandinka\n)', 'mnw (Mon\n)', 'mnx (Sougb\n)', 'moa (Mwan\n)', 'mog (Mongondow\n)', 'mon (Mongolian\n)', 'mop (Maya, Mopán\n)', 'mor (Moro\n)', 'mos (Mòoré\n)', 'mox (Molima\n)', 'moz (Mukulu\n)', 'mpg (Marba\n)', 'mpm (Mixtec, Yosondúa\n)', 'mpp (Migabac\n)', 'mpx (Misima-Panaeati\n)', 'mqb (Mbuko\n)', 'mqf (Momuna\n)', 'mqj (Mamasa\n)', 'mqn (Moronene\n)', 'mri (Maori\n)', 'mrw (Maranao\n)', 'msy (Aruamu\n)', 'mtd (Mualang\n)', 'mtj (Moskona\n)', 'mto (Mixe, Totontepec\n)', 'muh (Mündü\n)', 'mup (Malvi\n)', 'mur (Murle\n)', 'muv (Muthuvan\n)', 'muy (Muyang\n)', 'mvp (Duri\n)', 'mwq (Chin, Müün\n)', 'mwv (Mentawai\n)', 'mxb (Mixtec, Tezoatlán\n)', 'mxq (Mixe, Juquila\n)', 'mxt (Mixtec, Jamiltepec\n)', 'mxv (Mixtec, Metlatónoc\n)', 'mya (Burmese\n)', 'myb (Mbay\n)', 'myk (Sénoufo, Mamara\n)', 'myl (Moma\n)', 'myv (Erzya\n)', 'myx (Masaaba\n)', 'myy (Macuna\n)', 'mza (Mixtec, Santa María Zacatepec\n)', 'mzi (Mazatec, Ixcatlán\n)', 'mzj (Manya\n)', 'mzk (Mambila, Nigeria\n)', 'mzm (Mumuye\n)', 'mzw (Deg\n)', 'nab (Nambikuára, Southern\n)', 'nag (Nagamese\n)', 'nan (Chinese, Min Nan\n)', 'nas (Naasioi\n)', 'naw (Nawuri\n)', 'nca (Iyo\n)', 'nch (Nahuatl, Central Huasteca\n)', 'ncj (Nahuatl, Northern Puebla\n)', 'ncl (Nahuatl, Michoacán\n)', 'ncu (Chumburung\n)', 'ndj (Ndamba\n)', 'ndp (Kebu\n)', 'ndv (Ndut\n)', 'ndy (Lutos\n)', 'ndz (Ndogo\n)', 'neb (Toura\n)', 'new (Newar\n)', 'nfa (Dhao\n)', 'nfr (Nafaanra\n)', 'nga (Ngbaka\n)', 'ngl (Lomwe\n)', 'ngp (Ngulu\n)', 'ngu (Nahuatl, Guerrero\n)', 'nhe (Nahuatl, Eastern Huasteca\n)', 'nhi (Nahuatl, Zacatlán-Ahuacatlán-Tepetzintla\n)', 'nhu (Noone\n)', 'nhw (Nahuatl, Western Huasteca\n)', 'nhx (Nahuatl, Isthmus-Mecayapan\n)', 'nhy (Nahuatl, Northern Oaxaca\n)', 'nia (Nias\n)', 'nij (Ngaju\n)', 'nim (Nilamba\n)', 'nin (Ninzo\n)', 'nko (Nkonya\n)', 'nlc (Nalca\n)', 'nld (Dutch\n)', 'nlg (Gela\n)', 'nlk (Yali, Ninia\n)', 'nmz (Nawdm\n)', 'nnb (Nande\n)', 'nno (Norwegian Nynorsk\n)', 'nnq (Ngindo\n)', 'nnw (Nuni, Southern\n)', 'noa (Woun Meu\n)', 'nob (Norwegian Bokmål\n)', 'nod (Thai, Northern\n)', 'nog (Nogai\n)', 'not (Nomatsigenga\n)', 'npi (Nepali\n)', 'npl (Nahuatl, Southeastern Puebla\n)', 'npy (Napu\n)', 'nso (Sotho, Northern\n)', 'nst (Naga, Tangshang\n)', 'nsu (Nahuatl, Sierra Negra\n)', 'ntm (Nateni\n)', 'ntr (Delo\n)', 'nuj (Nyole\n)', 'nus (Nuer\n)', 'nuz (Nahuatl, Tlamacazapa\n)', 'nwb (Nyabwa\n)', 'nxq (Naxi\n)', 'nya (Chichewa\n)', 'nyf (Kigiryama\n)', 'nyn (Nyankore\n)', 'nyo (Nyoro\n)', 'nyy (Nyakyusa-Ngonde\n)', 'nzi (Nzema\n)', 'obo (Manobo, Obo\n)', 'oci (Occitan\n)', 'ojb-script_latin (Ojibwa, Northwestern\n)', 'ojb-script_syllabics (Ojibwa, Northwestern\n)', 'oku (Oku\n)', 'old (Mochi\n)', 'omw (Tairora, South\n)', 'onb (Lingao\n)', 'ood (Tohono O’odham\n)', 'orm (Oromo\n)', 'ory (Odia\n)', 'oss (Ossetic\n)', 'ote (Otomi, Mezquital\n)', 'otq (Otomi, Querétaro\n)', 'ozm (Koonzime\n)', 'pab (Parecís\n)', 'pad (Paumarí\n)', 'pag (Pangasinan\n)', 'pam (Kapampangan\n)', 'pan (Punjabi, Eastern\n)', 'pao (Paiute, Northern\n)', 'pap (Papiamentu\n)', 'pau (Palauan\n)', 'pbb (Nasa\n)', 'pbc (Patamona\n)', 'pbi (Parkwa\n)', 'pce (Palaung, Ruching\n)', 'pcm (Pidgin, Nigerian\n)', 'peg (Pengo\n)', 'pez (Penan, Eastern\n)', 'pib (Yine\n)', 'pil (Yom\n)', 'pir (Piratapuyo\n)', 'pis (Pijin\n)', 'pjt (Pitjantjatjara\n)', 'pkb (Kipfokomo\n)', 'pls (Popoloca, San Marcos Tlacoyalco\n)', 'plw (Palawano, Brooke’s Point\n)', 'pmf (Pamona\n)', 'pny (Pinyin\n)', 'poh-dialect_eastern (Poqomchi’\n)', 'poh-dialect_western (Poqomchi’\n)', 'poi (Popoluca, Highland\n)', 'pol (Polish\n)', 'por (Portuguese\n)', 'poy (Pogolo\n)', 'ppk (Uma\n)', 'pps (Popoloca, San Luís Temalacayuca\n)', 'prf (Paranan\n)', 'prk (Wa, Parauk\n)', 'prt (Prai\n)', 'pse (Malay, Central\n)', 'pss (Kaulong\n)', 'ptu (Bambam\n)', 'pui (Puinave\n)', 'pus (Pushto\n)', 'pwg (Gapapaiwa\n)', 'pww (Karen, Pwo Northern\n)', 'pxm (Mixe, Quetzaltepec\n)', 'qub (Quechua, Huallaga\n)', 'quc-dialect_central (K’iche’\n)', 'quc-dialect_east (K’iche’\n)', 'quc-dialect_north (K’iche’\n)', 'quf (Quechua, Lambayeque\n)', 'quh (Quechua, South Bolivian\n)', 'qul (Quechua, North Bolivian\n)', 'quw (Quichua, Tena Lowland\n)', 'quy (Quechua, Ayacucho\n)', 'quz (Quechua, Cusco\n)', 'qvc (Quechua, Cajamarca\n)', 'qve (Quechua, Eastern Apurímac\n)', 'qvh (Quechua, Huamalíes-Dos de Mayo Huánuco\n)', 'qvm (Quechua, Margos-Yarowilca-Lauricocha\n)', 'qvn (Quechua, North Junín\n)', 'qvo (Quichua, Napo\n)', 'qvs (Quechua, San Martín\n)', 'qvw (Quechua, Huaylla Wanca\n)', 'qvz (Quichua, Northern Pastaza\n)', 'qwh (Quechua, Huaylas Ancash\n)', 'qxh (Quechua, Panao\n)', 'qxl (Quichua, Salasaca Highland\n)', 'qxn (Quechua, Northern Conchucos Ancash\n)', 'qxo (Quechua, Southern Conchucos\n)', 'qxr (Quichua, Cañar Highland\n)', 'rah (Rabha\n)', 'rai (Ramoaaina\n)', 'rap (Rapa Nui\n)', 'rav (Sampang\n)', 'raw (Rawang\n)', 'rej (Rejang\n)', 'rel (Rendille\n)', 'rgu (Rikou\n)', 'rhg (Rohingya\n)', 'rif-script_arabic (Tarifit\n)', 'rif-script_latin (Tarifit\n)', 'ril (Riang Lang\n)', 'rim (Nyaturu\n)', 'rjs (Rajbanshi\n)', 'rkt (Rangpuri\n)', 'rmc-script_cyrillic (Romani, Carpathian\n)', 'rmc-script_latin (Romani, Carpathian\n)', 'rmo (Romani, Sinte\n)', 'rmy-script_cyrillic (Romani, Vlax\n)', 'rmy-script_latin (Romani, Vlax\n)', 'rng (Ronga\n)', 'rnl (Ranglong\n)', 'roh-dialect_sursilv (Romansh\n)', 'roh-dialect_vallader (Romansh\n)', 'rol (Romblomanon\n)', 'ron (Romanian\n)', 'rop (Kriol\n)', 'rro (Waima\n)', 'rub (Gungu\n)', 'ruf (Luguru\n)', 'rug (Roviana\n)', 'run (Rundi\n)', 'rus (Russian\n)', 'sab (Buglere\n)', 'sag (Sango\n)', 'sah (Yakut\n)', 'saj (Sahu\n)', 'saq (Samburu\n)', 'sas (Sasak\n)', 'sat (Santhali\n)', 'sba (Ngambay\n)', 'sbd (Samo, Southern\n)', 'sbl (Sambal, Botolan\n)', 'sbp (Sangu\n)', 'sch (Sakachep\n)', 'sck (Sadri\n)', 'sda (Toraja-Sa’dan\n)', 'sea (Semai\n)', 'seh (Sena\n)', 'ses (Songhay, Koyraboro Senni\n)', 'sey (Paicoca\n)', 'sgb (Ayta, Mag-antsi\n)', 'sgj (Surgujia\n)', 'sgw (Sebat Bet Gurage\n)', 'shi (Tachelhit\n)', 'shk (Shilluk\n)', 'shn (Shan\n)', 'sho (Shanga\n)', 'shp (Shipibo-Conibo\n)', 'sid (Sidamo\n)', 'sig (Paasaal\n)', 'sil (Sisaala, Tumulung\n)', 'sja (Epena\n)', 'sjm (Mapun\n)', 'sld (Sissala\n)', 'slk (Slovak\n)', 'slu (Selaru\n)', 'slv (Slovene\n)', 'sml (Sama, Central\n)', 'smo (Samoan\n)', 'sna (Shona\n)', 'snd (Sindhi\n)', 'sne (Bidayuh, Bau\n)', 'snn (Siona\n)', 'snp (Siane\n)', 'snw (Selee\n)', 'som (Somali\n)', 'soy (Miyobe\n)', 'spa (Spanish\n)', 'spp (Sénoufo, Supyire\n)', 'spy (Sabaot\n)', 'sqi (Albanian\n)', 'sri (Siriano\n)', 'srm (Saramaccan\n)', 'srn (Sranan Tongo\n)', 'srp-script_cyrillic (Serbian\n)', 'srp-script_latin (Serbian\n)', 'srx (Sirmauri\n)', 'stn (Owa\n)', 'stp (Tepehuan, Southeastern\n)', 'suc (Subanon, Western\n)', 'suk (Sukuma\n)', 'sun (Sunda\n)', 'sur (Mwaghavul\n)', 'sus (Susu\n)', 'suv (Puroik\n)', 'suz (Sunwar\n)', 'swe (Swedish\n)', 'swh (Swahili\n)', 'sxb (Suba\n)', 'sxn (Sangir\n)', 'sya (Siang\n)', 'syl (Sylheti\n)', 'sza (Semelai\n)', 'tac (Tarahumara, Western\n)', 'taj (Tamang, Eastern\n)', 'tam (Tamil\n)', 'tao (Yami\n)', 'tap (Taabwa\n)', 'taq (Tamasheq\n)', 'tat (Tatar\n)', 'tav (Tatuyo\n)', 'tbc (Takia\n)', 'tbg (Tairora, North\n)', 'tbk (Tagbanwa, Calamian\n)', 'tbl (Tboli\n)', 'tby (Tabaru\n)', 'tbz (Ditammari\n)', 'tca (Ticuna\n)', 'tcc (Datooga\n)', 'tcs (Torres Strait Creole\n)', 'tcz (Chin, Thado\n)', 'tdj (Tajio\n)', 'ted (Krumen, Tepo\n)', 'tee (Tepehua, Huehuetla\n)', 'tel (Telugu\n)', 'tem (Themne\n)', 'teo (Ateso\n)', 'ter (Terêna\n)', 'tes (Tengger\n)', 'tew (Tewa\n)', 'tex (Tennet\n)', 'tfr (Teribe\n)', 'tgj (Tagin\n)', 'tgk (Tajik\n)', 'tgl (Tagalog\n)', 'tgo (Sudest\n)', 'tgp (Tangoa\n)', 'tha (Thai\n)', 'thk (Kitharaka\n)', 'thl (Tharu, Dangaura\n)', 'tih (Murut, Timugon\n)', 'tik (Tikar\n)', 'tir (Tigrigna\n)', 'tkr (Tsakhur\n)', 'tlb (Tobelo\n)', 'tlj (Talinga-Bwisi\n)', 'tly (Talysh\n)', 'tmc (Tumak\n)', 'tmf (Toba-Maskoy\n)', 'tna (Tacana\n)', 'tng (Tobanga\n)', 'tnk (Kwamera\n)', 'tnn (Tanna, North\n)', 'tnp (Whitesands\n)', 'tnr (Ménik\n)', 'tnt (Tontemboan\n)', 'tob (Toba\n)', 'toc (Totonac, Coyutla\n)', 'toh (Tonga\n)', 'tom (Tombulu\n)', 'tos (Totonac, Highland\n)', 'tpi (Tok Pisin\n)', 'tpm (Tampulma\n)', 'tpp (Tepehua, Pisaflores\n)', 'tpt (Tepehua, Tlachichilco\n)', 'trc (Triqui, Copala\n)', 'tri (Trió\n)', 'trn (Trinitario\n)', 'trs (Triqui, Chicahuaxtla\n)', 'tso (Tsonga\n)', 'tsz (Purepecha\n)', 'ttc (Tektiteko\n)', 'tte (Bwanabwana\n)', 'ttq-script_tifinagh (Tamajaq, Tawallammat\n)', 'tue (Tuyuca\n)', 'tuf (Tunebo, Central\n)', 'tuk-script_arabic (Turkmen\n)', 'tuk-script_latin (Turkmen\n)', 'tuo (Tucano\n)', 'tur (Turkish\n)', 'tvw (Sedoa\n)', 'twb (Tawbuid\n)', 'twe (Teiwa\n)', 'twu (Termanu\n)', 'txa (Tombonuo\n)', 'txq (Tii\n)', 'txu (Kayapó\n)', 'tye (Kyanga\n)', 'tzh-dialect_bachajon (Tzeltal\n)', 'tzh-dialect_tenejapa (Tzeltal\n)', 'tzj-dialect_eastern (Tz’utujil\n)', 'tzj-dialect_western (Tz’utujil\n)', 'tzo-dialect_chamula (Tzotzil\n)', 'tzo-dialect_chenalho (Tzotzil\n)', 'ubl (Bikol, Buhi’non\n)', 'ubu (Umbu-Ungu\n)', 'udm (Udmurt\n)', 'udu (Uduk\n)', 'uig-script_arabic (Uyghur\n)', 'uig-script_cyrillic (Uyghur\n)', 'ukr (Ukrainian\n)', 'umb (Umbundu\n)', 'unr (Mundari\n)', 'upv (Uripiv-Wala-Rano-Atchin\n)', 'ura (Urarina\n)', 'urb (Kaapor\n)', 'urd-script_arabic (Urdu\n)', 'urd-script_devanagari (Urdu\n)', 'urd-script_latin (Urdu\n)', 'urk (Urak Lawoi’\n)', 'urt (Urat\n)', 'ury (Orya\n)', 'usp (Uspanteko\n)', 'uzb-script_cyrillic (Uzbek\n)', 'uzb-script_latin (Uzbek\n)', 'vag (Vagla\n)', 'vid (Vidunda\n)', 'vie (Vietnamese\n)', 'vif (Vili\n)', 'vmw (Makhuwa\n)', 'vmy (Mazatec, Ayautla\n)', 'vot (Vod\n)', 'vun (Vunjo\n)', 'vut (Vute\n)', 'wal-script_ethiopic (Wolaytta\n)', 'wal-script_latin (Wolaytta\n)', 'wap (Wapishana\n)', 'war (Waray-Waray\n)', 'waw (Waiwai\n)', 'way (Wayana\n)', 'wba (Warao\n)', 'wlo (Wolio\n)', 'wlx (Wali\n)', 'wmw (Mwani\n)', 'wob (Wè Northern\n)', 'wol (Wolof\n)', 'wsg (Gondi, Adilabad\n)', 'wwa (Waama\n)', 'xal (Kalmyk-Oirat\n)', 'xdy (Malayic Dayak\n)', 'xed (Hdi\n)', 'xer (Xerénte\n)', 'xho (Xhosa\n)', 'xmm (Malay, Manado\n)', 'xnj (Chingoni\n)', 'xnr (Kangri\n)', 'xog (Soga\n)', 'xon (Konkomba\n)', 'xrb (Karaboro, Eastern\n)', 'xsb (Sambal\n)', 'xsm (Kasem\n)', 'xsr (Sherpa\n)', 'xsu (Sanumá\n)', 'xta (Mixtec, Alcozauca\n)', 'xtd (Mixtec, Diuxi-Tilantongo\n)', 'xte (Ketengban\n)', 'xtm (Mixtec, Magdalena Peñasco\n)', 'xtn (Mixtec, Northern Tlaxiaco\n)', 'xua (Kurumba, Alu\n)', 'xuo (Kuo\n)', 'yaa (Yaminahua\n)', 'yad (Yagua\n)', 'yal (Yalunka\n)', 'yam (Yamba\n)', 'yao (Yao\n)', 'yas (Nugunu\n)', 'yat (Yambeta\n)', 'yaz (Lokaa\n)', 'yba (Yala\n)', 'ybb (Yemba\n)', 'ycl (Lolopo\n)', 'ycn (Yucuna\n)', 'yea (Ravula\n)', 'yka (Yakan\n)', 'yli (Yali, Angguruk\n)', 'yor (Yoruba\n)', 'yre (Yaouré\n)', 'yua (Maya, Yucatec\n)', 'yue-script_traditional (Chinese, Yue\n)', 'yuz (Yuracare\n)', 'yva (Yawa\n)', 'zaa (Zapotec, Sierra de Juárez\n)', 'zab (Zapotec, Western Tlacolula Valley\n)', 'zac (Zapotec, Ocotlán\n)', 'zad (Zapotec, Cajonos\n)', 'zae (Zapotec, Yareni\n)', 'zai (Zapotec, Isthmus\n)', 'zam (Zapotec, Miahuatlán\n)', 'zao (Zapotec, Ozolotepec\n)', 'zaq (Zapotec, Aloápam\n)', 'zar (Zapotec, Rincón\n)', 'zas (Zapotec, Santo Domingo Albarradas\n)', 'zav (Zapotec, Yatzachi\n)', 'zaw (Zapotec, Mitla\n)', 'zca (Zapotec, Coatecas Altas\n)', 'zga (Kinga\n)', 'zim (Mesme\n)', 'ziw (Zigula\n)', 'zlm (Malay\n)', 'zmz (Mbandja\n)', 'zne (Zande\n)', 'zos (Zoque, Francisco León\n)', 'zpc (Zapotec, Choapan\n)', 'zpg (Zapotec, Guevea de Humboldt\n)', 'zpi (Zapotec, Santa María Quiegolani\n)', 'zpl (Zapotec, Lachixío\n)', 'zpm (Zapotec, Mixtepec\n)', 'zpo (Zapotec, Amatlán\n)', 'zpt (Zapotec, San Vicente Coatlán\n)', 'zpu (Zapotec, Yalálag\n)', 'zpz (Zapotec, Texmelucan\n)', 'ztq (Zapotec, Quioquitani-Quierí\n)', 'zty (Zapotec, Yatee\n)', 'zul (Zulu\n)', 'zyb (Zhuang, Yongbei\n)', 'zyp (Chin, Zyphe\n)', 'zza (Zaza)']  # fmt: skip
MMS_SUPPORTED_CODES = list(map(lambda x: x[:3], MMS_SUPPORTED))


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
    mms_large = "MMS-Large (Meta)"

    def supports_auto_detect(self) -> bool:
        return self not in {self.azure, self.gcp_v1, self.mms_large}


asr_model_ids = {
    AsrModels.whisper_large_v3: "vaibhavs10/incredibly-fast-whisper:37dfc0d6a7eb43ff84e230f74a24dab84e6bb7756c9b457dbdcceca3de7a4a04",
    AsrModels.whisper_large_v2: "openai/whisper-large-v2",
    AsrModels.whisper_hindi_large_v2: "vasista22/whisper-hindi-large-v2",
    AsrModels.whisper_telugu_large_v2: "vasista22/whisper-telugu-large-v2",
    AsrModels.vakyansh_bhojpuri: "Harveenchadha/vakyansh-wav2vec2-bhojpuri-bhom-60",
    AsrModels.nemo_english: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/english_large_data_fixed.nemo",
    AsrModels.nemo_hindi: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/stt_hi_conformer_ctc_large_v2.nemo",
    AsrModels.seamless_m4t: "facebook/hf-seamless-m4t-large",
    AsrModels.mms_large: "https://mms-meta-mms.hf.space/",
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
    AsrModels.mms_large: MMS_SUPPORTED_CODES,
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
    if allow_none:
        options.insert(0, None)
    return st.selectbox(
        label=label,
        key=key,
        format_func=lambda k: languages[k] if k else "———",
        options=options,
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


def get_language_in_collection(langcode: str, languages):
    import langcodes

    for lang in languages:
        if langcodes.get(lang).language == langcodes.get(langcode).language:
            return langcode
    return None


def asr_language_selector(
    selected_model: AsrModels,
    label="##### Spoken Language",
    key="language",
):
    import langcodes

    # don't show language selector for models with forced language
    forced_lang = forced_asr_languages.get(selected_model)
    if forced_lang:
        st.session_state[key] = forced_lang
        return forced_lang

    options = list(asr_supported_languages.get(selected_model, []))
    if selected_model and selected_model.supports_auto_detect():
        options.insert(0, None)

    # handle non-canonical language codes
    old_val = st.session_state.get(key)
    if old_val and old_val not in options:
        lobj = langcodes.Language.get(old_val)
        for opt in options:
            if opt and langcodes.Language.get(opt).language == lobj.language:
                st.session_state[key] = opt
                break

    return st.selectbox(
        label=label,
        key=key,
        format_func=lambda l: (
            f"{langcodes.Language.get(l).display_name()} | {l}" if l else "Auto Detect"
        ),
        options=options,
    )


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
    import langcodes

    # convert to BCP-47 format (google handles consistent language codes but sometimes gets confused by a mix of iso2 and iso3 which we have)
    if source_language:
        source_language = langcodes.Language.get(source_language).to_tag()
        source_language = get_language_in_collection(
            source_language, google_translate_source_languages().keys()
        )  # this will default to autodetect if language is not found as supported
    target_language = langcodes.Language.get(target_language).to_tag()
    target_language: str | None = get_language_in_collection(
        target_language, google_translate_target_languages().keys()
    )
    if not target_language:
        raise UserError(f"Unsupported target language: {target_language!r}")

    # if the language supports transliteration, we should check if the script is Latin
    if source_language and source_language not in TRANSLITERATION_SUPPORTED:
        language_codes = [source_language] * len(texts)
    else:
        translate_client = translate.Client()
        detections = flatten(
            translate_client.detect_language(texts[i : i + TRANSLATE_DETECT_BATCH_SIZE])
            for i in range(0, len(texts), TRANSLATE_DETECT_BATCH_SIZE)
        )
        language_codes = [detection["language"] for detection in detections]

    return map_parallel(
        lambda text, source: _translate_text(
            text, source, target_language, glossary_url
        ),
        texts,
        language_codes,
        max_workers=TRANSLATE_DETECT_BATCH_SIZE,
    )


def _translate_text(
    text: str,
    source_language: str,
    target_language: str,
    glossary_url: str | None,
) -> str:
    is_romanized = source_language.endswith("-Latn")
    source_language = source_language.replace("-Latn", "")
    enable_transliteration = (
        is_romanized and source_language in TRANSLITERATION_SUPPORTED
    )

    # prevent incorrect API calls
    if not text or source_language == target_language or source_language == "und":
        return text

    if source_language == "wo-SN" or target_language == "wo-SN":
        return _MinT_translate_one_text(text, source_language, target_language)

    config = {
        "target_language_code": target_language,
        "contents": text,
        "mime_type": "text/plain",
        "transliteration_config": {"enable_transliteration": enable_transliteration},
    }
    if source_language != "auto":
        config["source_language_code"] = source_language

    # glossary does not work with transliteration
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
    elif selected_model == AsrModels.mms_large:
        from gradio_client import Client

        client = Client(asr_model_ids[AsrModels.mms_large])
        lang_id = MMS_SUPPORTED[MMS_SUPPORTED_CODES.index(language)]
        result = client.predict(
            "Record from Mic", audio_url, audio_url, lang_id, api_name="/predict"
        )
        return str(result)
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
    # check if we should use the fast queue
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


def download_youtube_to_wav(youtube_url: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        infile = os.path.join(tmpdir, "infile")
        outfile = os.path.join(tmpdir, "outfile.wav")
        # run yt-dlp to download audio
        call_cmd(
            "yt-dlp",
            "--no-playlist",
            "--format",
            "bestaudio",
            "--output",
            infile,
            youtube_url,
        )
        # convert audio to single channel wav
        ffmpeg("-i", infile, *FFMPEG_WAV_ARGS, outfile)
        # read wav file into memory
        with open(outfile, "rb") as f:
            wavdata = f.read()
    return wavdata


def audio_url_to_wav(audio_url: str) -> tuple[str, int]:
    r = requests.get(audio_url)
    raise_for_status(r)

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


def format_timestamp(seconds: float, always_include_hours: bool, decimal_marker: str):
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
