from itertools import zip_longest
from textwrap import dedent

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from furl import furl
import langcodes

import gooey_ui as st
from app_users.models import AppUser
from bots.models import BotIntegration, BotIntegrationAnalysisRun, Platform
from daras_ai_v2 import settings, icons
from daras_ai_v2.api_examples_widget import bot_api_example_generator
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.workflow_url_input import workflow_url_input
from recipes.BulkRunner import list_view_editor
from recipes.CompareLLM import CompareLLMPage
from routers.root import RecipeTabs, chat_route, chat_lib_route

TWILIO_SUPPORTED_VOICES = ["Google.af-ZA-Standard-A", "Polly.Zeina", "Google.ar-XA-Standard-A", "Google.ar-XA-Standard-B", "Google.ar-XA-Standard-C", "Google.ar-XA-Standard-D", "Google.ar-XA-Wavenet-A", "Google.ar-XA-Wavenet-B", "Google.ar-XA-Wavenet-C", "Google.ar-XA-Wavenet-D", "Polly.Hala-Neural", "Polly.Zayd-Neural", "Google.eu-ES-Standard-A", "Google.bn-IN-Standard-C", "Google.bn-IN-Standard-D", "Google.bn-IN-Wavenet-C", "Google.bn-IN-Wavenet-D", "Google.bg-BG-Standard-A", "Polly.Arlet-Neural", "Google.ca-ES-Standard-A", "Polly.Hiujin-Neural", "Google.yue-HK-Standard-A", "Google.yue-HK-Standard-B", "Google.yue-HK-Standard-C", "Google.yue-HK-Standard-D", "Polly.Zhiyu", "Polly.Zhiyu-Neural", "Google.cmn-CN-Standard-A", "Google.cmn-CN-Standard-B", "Google.cmn-CN-Standard-C", "Google.cmn-CN-Standard-D", "Google.cmn-CN-Wavenet-A", "Google.cmn-CN-Wavenet-B", "Google.cmn-CN-Wavenet-C", "Google.cmn-CN-Wavenet-D", "Google.cmn-TW-Standard-A", "Google.cmn-TW-Standard-B", "Google.cmn-TW-Standard-C", "Google.cmn-TW-Wavenet-A", "Google.cmn-TW-Wavenet-B", "Google.cmn-TW-Wavenet-C", "Google.cs-CZ-Standard-A", "Google.cs-CZ-Wavenet-A", "Polly.Mads", "Polly.Naja", "Polly.Sofie-Neural", "Google.da-DK-Standard-A", "Google.da-DK-Standard-C", "Google.da-DK-Standard-D", "Google.da-DK-Standard-E", "Google.da-DK-Wavenet-A", "Google.da-DK-Wavenet-C", "Google.da-DK-Wavenet-D", "Google.da-DK-Wavenet-E", "Polly.Lisa-Neural", "Google.nl-BE-Standard-A", "Google.nl-BE-Standard-B", "Google.nl-BE-Wavenet-A", "Google.nl-BE-Wavenet-B", "Polly.Lotte", "Polly.Ruben", "Polly.Laura-Neural", "Google.nl-NL-Standard-A", "Google.nl-NL-Standard-B", "Google.nl-NL-Standard-C", "Google.nl-NL-Standard-D", "Google.nl-NL-Standard-E", "Google.nl-NL-Wavenet-A", "Google.nl-NL-Wavenet-B", "Google.nl-NL-Wavenet-C", "Google.nl-NL-Wavenet-D", "Google.nl-NL-Wavenet-E", "Polly.Nicole", "Polly.Russell", "Polly.Olivia-Neural", "Google.en-AU-Standard-A", "Google.en-AU-Standard-B", "Google.en-AU-Standard-C", "Google.en-AU-Standard-D", "Google.en-AU-Wavenet-A", "Google.en-AU-Wavenet-B", "Google.en-AU-Wavenet-C", "Google.en-AU-Wavenet-D", "Google.en-AU-Neural2-A", "Google.en-AU-Neural2-B", "Google.en-AU-Neural2-C", "Google.en-AU-Neural2-D", "Polly.Raveena", "Google.en-IN-Standard-A", "Google.en-IN-Standard-B", "Google.en-IN-Standard-C", "Google.en-IN-Standard-D", "Google.en-IN-Wavenet-A", "Google.en-IN-Wavenet-B", "Google.en-IN-Wavenet-C", "Google.en-IN-Wavenet-D", "Google.en-IN-Neural2-A", "Google.en-IN-Neural2-B", "Google.en-IN-Neural2-C", "Google.en-IN-Neural2-D", "Polly.Niamh-Neural", "Polly.Aria-Neural", "Polly.Ayanda-Neural", "Polly.Amy", "Polly.Brian", "Polly.Emma", "Polly.Amy-Neural", "Polly.Emma-Neural", "Polly.Brian-Neural", "Polly.Arthur-Neural", "Google.en-GB-Standard-A", "Google.en-GB-Standard-B", "Google.en-GB-Standard-C", "Google.en-GB-Standard-D", "Google.en-GB-Standard-F", "Google.en-GB-Wavenet-A", "Google.en-GB-Wavenet-B", "Google.en-GB-Wavenet-C", "Google.en-GB-Wavenet-D", "Google.en-GB-Wavenet-F", "Google.en-GB-Neural2-A", "Google.en-GB-Neural2-B", "Google.en-GB-Neural2-C", "Google.en-GB-Neural2-D", "Google.en-GB-Neural2-F", "Polly.Ivy", "Polly.Joanna", "Polly.Joey", "Polly.Justin", "Polly.Kendra", "Polly.Kimberly", "Polly.Matthew", "Polly.Salli", "child)	Polly.Ivy-Neural", "Polly.Joanna-Neural*", "Polly.Kendra-Neural", "child)	Polly.Kevin-Neural", "Polly.Kimberly-Neural", "Polly.Salli-Neural", "Polly.Joey-Neural", "child)	Polly.Justin-Neural", "Polly.Matthew-Neural*", "Polly.Ruth-Neural", "Polly.Stephen-Neural", "Polly.Gregory-Neural", "Polly.Danielle-Neural", "Google.en-US-Standard-A", "Google.en-US-Standard-B", "Google.en-US-Standard-C", "Google.en-US-Standard-D", "Google.en-US-Standard-E", "Google.en-US-Standard-F", "Google.en-US-Standard-G", "Google.en-US-Standard-H", "Google.en-US-Standard-I", "Google.en-US-Standard-J", "Google.en-US-Wavenet-A", "Google.en-US-Wavenet-B", "Google.en-US-Wavenet-C", "Google.en-US-Wavenet-D", "Google.en-US-Wavenet-E", "Google.en-US-Wavenet-F", "Google.en-US-Wavenet-G", "Google.en-US-Wavenet-H", "Google.en-US-Wavenet-I", "Google.en-US-Wavenet-J", "Google.en-US-Neural2-A", "Google.en-US-Neural2-C", "Google.en-US-Neural2-D", "Google.en-US-Neural2-E", "Google.en-US-Neural2-F", "Google.en-US-Neural2-G", "Google.en-US-Neural2-H", "Google.en-US-Neural2-I", "Google.en-US-Neural2-J", "Polly.Geraint", "Google.fil-PH-Standard-A", "Google.fil-PH-Standard-B", "Google.fil-PH-Standard-C", "Google.fil-PH-Standard-D", "Google.fil-PH-Wavenet-A", "Google.fil-PH-Wavenet-B", "Google.fil-PH-Wavenet-C", "Google.fil-PH-Wavenet-D", "Polly.Suvi-Neural", "Google.fi-FI-Standard-A", "Google.fi-FI-Wavenet-A", "Polly.Isabelle-Neural", "Polly.Chantal", "Polly.Gabrielle-Neural", "Polly.Liam-Neural", "Google.fr-CA-Standard-A", "Google.fr-CA-Standard-B", "Google.fr-CA-Standard-C", "Google.fr-CA-Standard-D", "Google.fr-CA-Wavenet-A", "Google.fr-CA-Wavenet-B", "Google.fr-CA-Wavenet-C", "Google.fr-CA-Wavenet-D", "Google.fr-CA-Neural2-A", "Google.fr-CA-Neural2-B", "Google.fr-CA-Neural2-C", "Google.fr-CA-Neural2-D", "Polly.Céline/Polly.Celine", "Polly.Léa/Polly.Lea", "Polly.Mathieu", "Polly.Lea-Neural", "Polly.Remi-Neural", "Google.fr-FR-Standard-A", "Google.fr-FR-Standard-B", "Google.fr-FR-Standard-C", "Google.fr-FR-Standard-D", "Google.fr-FR-Standard-E", "Google.fr-FR-Wavenet-A", "Google.fr-FR-Wavenet-B", "Google.fr-FR-Wavenet-C", "Google.fr-FR-Wavenet-D", "Google.fr-FR-Wavenet-E", "Google.fr-FR-Neural2-A", "Google.fr-FR-Neural2-B", "Google.fr-FR-Neural2-C", "Google.fr-FR-Neural2-D", "Google.fr-FR-Neural2-E", "Google.gl-ES-Standard-A", "Polly.Hannah-Neural", "Polly.Hans", "Polly.Marlene", "Polly.Vicki", "Polly.Vicki-Neural", "Polly.Daniel-Neural", "Google.de-DE-Standard-A", "Google.de-DE-Standard-B", "Google.de-DE-Standard-C", "Google.de-DE-Standard-D", "Google.de-DE-Standard-E", "Google.de-DE-Standard-F", "Google.de-DE-Wavenet-A", "Google.de-DE-Wavenet-B", "Google.de-DE-Wavenet-C", "Google.de-DE-Wavenet-D", "Google.de-DE-Wavenet-E", "Google.de-DE-Wavenet-F", "Google.de-DE-Neural2-A", "Google.de-DE-Neural2-B", "Google.de-DE-Neural2-C", "Google.de-DE-Neural2-D", "Google.de-DE-Neural2-F", "Google.el-GR-Standard-A", "Google.el-GR-Wavenet-A", "Google.gu-IN-Standard-C", "Google.gu-IN-Standard-D", "Google.gu-IN-Wavenet-C", "Google.gu-IN-Wavenet-D", "Google.he-IL-Standard-A", "Google.he-IL-Standard-B", "Google.he-IL-Standard-C", "Google.he-IL-Standard-D", "Google.he-IL-Wavenet-A", "Google.he-IL-Wavenet-B", "Google.he-IL-Wavenet-C", "Google.he-IL-Wavenet-D", "Polly.Aditi", "Polly.Kajal-Neural", "Google.hi-IN-Standard-A", "Google.hi-IN-Standard-B", "Google.hi-IN-Standard-C", "Google.hi-IN-Standard-D", "Google.hi-IN-Wavenet-A", "Google.hi-IN-Wavenet-B", "Google.hi-IN-Wavenet-C", "Google.hi-IN-Wavenet-D", "Google.hi-IN-Neural2-A", "Google.hi-IN-Neural2-B", "Google.hi-IN-Neural2-C", "Google.hi-IN-Neural2-D", "Google.hu-HU-Standard-A", "Google.hu-HU-Wavenet-A", "Polly.Dóra/Polly.Dora", "Polly.Karl", "Google.is-IS-Standard-A", "Google.id-ID-Standard-A", "Google.id-ID-Standard-B", "Google.id-ID-Standard-C", "Google.id-ID-Standard-D", "Google.id-ID-Wavenet-A", "Google.id-ID-Wavenet-B", "Google.id-ID-Wavenet-C", "Google.id-ID-Wavenet-D", "Polly.Bianca", "Polly.Carla", "Polly.Giorgio", "Polly.Bianca-Neural", "Polly.Adriano-Neural", "Google.it-IT-Standard-B", "Google.it-IT-Standard-C", "Google.it-IT-Standard-D", "Google.it-IT-Wavenet-B", "Google.it-IT-Wavenet-C", "Google.it-IT-Wavenet-D", "Google.it-IT-Neural2-A", "Google.it-IT-Neural2-C", "Polly.Mizuki", "Polly.Takumi", "Polly.Takumi-Neural", "Polly.Kazuha-Neural", "Polly.Tomoko-Neural", "Google.ja-JP-Standard-B", "Google.ja-JP-Standard-C", "Google.ja-JP-Standard-D", "Google.ja-JP-Wavenet-B", "Google.ja-JP-Wavenet-C", "Google.ja-JP-Wavenet-D", "Google.kn-IN-Standard-C", "Google.kn-IN-Standard-D", "Google.kn-IN-Wavenet-C", "Google.kn-IN-Wavenet-D", "Polly.Seoyeon", "Polly.Seoyeon-Neural", "Google.ko-KR-Standard-A", "Google.ko-KR-Standard-B", "Google.ko-KR-Standard-C", "Google.ko-KR-Standard-D", "Google.ko-KR-Wavenet-A", "Google.ko-KR-Wavenet-B", "Google.ko-KR-Wavenet-C", "Google.ko-KR-Wavenet-D", "Google.ko-KR-Neural2-A", "Google.ko-KR-Neural2-B", "Google.ko-KR-Neural2-C", "Google.lv-LV-Standard-A", "Google.lt-LT-Standard-A", "Google.ms-MY-Standard-A", "Google.ms-MY-Standard-B", "Google.ms-MY-Standard-C", "Google.ms-MY-Standard-D", "Google.ms-MY-Wavenet-A", "Google.ms-MY-Wavenet-B", "Google.ms-MY-Wavenet-C", "Google.ms-MY-Wavenet-D", "Google.ml-IN-Wavenet-C", "Google.ml-IN-Wavenet-D", "Google.mr-IN-Standard-A", "Google.mr-IN-Standard-B", "Google.mr-IN-Standard-C", "Google.mr-IN-Wavenet-A", "Google.mr-IN-Wavenet-B", "Google.mr-IN-Wavenet-C", "Polly.Liv", "Polly.Ida-Neural", "Google.nb-NO-Standard-A", "Google.nb-NO-Standard-B", "Google.nb-NO-Standard-C", "Google.nb-NO-Standard-D", "Google.nb-NO-Standard-E", "Google.nb-NO-Wavenet-A", "Google.nb-NO-Wavenet-B", "Google.nb-NO-Wavenet-C", "Google.nb-NO-Wavenet-D", "Google.nb-NO-Wavenet-E", "Polly.Jacek", "Polly.Jan", "Polly.Ewa", "Polly.Maja", "Polly.Ola-Neural", "Google.pl-PL-Standard-A", "Google.pl-PL-Standard-B", "Google.pl-PL-Standard-C", "Google.pl-PL-Standard-D", "Google.pl-PL-Standard-E", "Google.pl-PL-Wavenet-A", "Google.pl-PL-Wavenet-B", "Google.pl-PL-Wavenet-C", "Google.pl-PL-Wavenet-D", "Google.pl-PL-Wavenet-E", "Polly.Camila", "Polly.Ricardo", "Polly.Vitória/Polly.Vitoria", "Polly.Camila-Neural", "Polly.Vitoria-Neural", "Polly.Thiago-Neural", "Google.pt-BR-Standard-B", "Google.pt-BR-Standard-C", "Google.pt-BR-Wavenet-B", "Google.pt-BR-Wavenet-C", "Google.pt-BR-Neural2-A", "Google.pt-BR-Neural2-B", "Google.pt-BR-Neural2-C", "Polly.Cristiano", "Polly.Inês/Polly.Ines", "Polly.Ines-Neural", "Google.pt-PT-Standard-A", "Google.pt-PT-Standard-B", "Google.pt-PT-Standard-C", "Google.pt-PT-Standard-D", "Google.pt-PT-Wavenet-A", "Google.pt-PT-Wavenet-B", "Google.pt-PT-Wavenet-C", "Google.pt-PT-Wavenet-D", "Google.pa-IN-Standard-A", "Google.pa-IN-Standard-B", "Google.pa-IN-Standard-C", "Google.pa-IN-Standard-D", "Google.pa-IN-Wavenet-A", "Google.pa-IN-Wavenet-B", "Google.pa-IN-Wavenet-C", "Google.pa-IN-Wavenet-D", "Polly.Carmen", "Google.ro-RO-Standard-A", "Google.ro-RO-Wavenet-A", "Polly.Maxim", "Polly.Tatyana", "Google.ru-RU-Standard-A", "Google.ru-RU-Standard-B", "Google.ru-RU-Standard-C", "Google.ru-RU-Standard-D", "Google.ru-RU-Standard-E", "Google.ru-RU-Wavenet-A", "Google.ru-RU-Wavenet-B", "Google.ru-RU-Wavenet-C", "Google.ru-RU-Wavenet-D", "Google.ru-RU-Wavenet-E", "Google.sr-RS-Standard-A", "Google.sk-SK-Standard-A", "Google.sk-SK-Wavenet-A", "Polly.Mia", "Polly.Mia-Neural", "Polly.Andres-Neural", "Polly.Conchita", "Polly.Enrique", "Polly.Lucia", "Polly.Lucia-Neural", "Polly.Sergio-Neural", "Google.es-ES-Standard-B", "Google.es-ES-Standard-C", "Google.es-ES-Standard-D", "Google.es-ES-Wavenet-B", "Google.es-ES-Wavenet-C", "Google.es-ES-Wavenet-D", "Google.es-ES-Neural2-A", "Google.es-ES-Neural2-B", "Google.es-ES-Neural2-C", "Google.es-ES-Neural2-D", "Google.es-ES-Neural2-E", "Google.es-ES-Neural2-F", "man", "woman", "Polly.Lupe", "Polly.Miguel", "Polly.Penélope/Polly.Penelope", "Polly.Lupe-Neural", "Polly.Pedro-Neural", "Google.es-US-Standard-A", "Google.es-US-Standard-B", "Google.es-US-Standard-C", "Google.es-US-Wavenet-A", "Google.es-US-Wavenet-B", "Google.es-US-Wavenet-C", "Google.es-US-Neural2-A", "Google.es-US-Neural2-B", "Google.es-US-Neural2-C", "Polly.Astrid", "Polly.Elin-Neural", "Google.sv-SE-Standard-A", "Google.sv-SE-Standard-B", "Google.sv-SE-Standard-C", "Google.sv-SE-Standard-D", "Google.sv-SE-Standard-E", "Google.sv-SE-Wavenet-A", "Google.sv-SE-Wavenet-B", "Google.sv-SE-Wavenet-C", "Google.sv-SE-Wavenet-D", "Google.sv-SE-Wavenet-E", "Google.ta-IN-Standard-C", "Google.ta-IN-Standard-D", "Google.ta-IN-Wavenet-C", "Google.ta-IN-Wavenet-D", "Google.te-IN-Standard-A", "Google.te-IN-Standard-B", "Google.th-TH-Standard-A", "Polly.Filiz", "Google.tr-TR-Standard-A", "Google.tr-TR-Standard-B", "Google.tr-TR-Standard-C", "Google.tr-TR-Standard-D", "Google.tr-TR-Standard-E", "Google.tr-TR-Wavenet-A", "Google.tr-TR-Wavenet-B", "Google.tr-TR-Wavenet-C", "Google.tr-TR-Wavenet-D", "Google.tr-TR-Wavenet-E", "Google.uk-UA-Standard-A", "Google.uk-UA-Wavenet-A", "Google.vi-VN-Standard-A", "Google.vi-VN-Standard-B", "Google.vi-VN-Standard-C", "Google.vi-VN-Standard-D", "Google.vi-VN-Wavenet-A", "Google.vi-VN-Wavenet-B", "Google.vi-VN-Wavenet-C", "Google.vi-VN-Wavenet-D", "Polly.Gwyneth"]  # fmt:skip
TWILIO_ASR_SUPPORTED_LANGUAGES = ["af-ZA", "am-ET", "hy-AM", "az-AZ", "id-ID", "ms-MY", "bn-BD", "bn-IN", "ca-ES", "cs-CZ", "da-DK", "de-DE", "en-AU", "en-CA", "en-GH", "en-GB", "en-IN", "en-IE", "en-KE", "en-NZ", "en-NG", "en-PH", "en-ZA", "en-TZ", "en-US", "es-AR", "es-BO", "es-CL", "es-CO", "es-CR", "es-EC", "es-SV", "es-ES", "es-US", "es-GT", "es-HN", "es-MX", "es-NI", "es-PA", "es-PY", "es-PE", "es-PR", "es-DO", "es-UY", "es-VE", "eu-ES", "fil-PH", "fr-CA", "fr-FR", "gl-ES", "ka-GE", "gu-IN", "hr-HR", "zu-ZA", "is-IS", "it-IT", "jv-ID", "kn-IN", "km-KH", "lo-LA", "lv-LV", "lt-LT", "hu-HU", "ml-IN", "mr-IN", "nl-NL", "ne-NP", "nb-NO", "pl-PL", "pt-BR", "pt-PT", "ro-RO", "si-LK", "sk-SK", "sl-SI", "su-ID", "sw-TZ", "sw-KE", "fi-FI", "sv-SE", "ta-IN", "ta-SG", "ta-LK", "ta-MY", "te-IN", "vi-VN", "tr-TR", "ur-PK", "ur-IN", "el-GR", "bg-BG", "ru-RU", "sr-RS", "uk-UA", "he-IL", "ar-IL", "ar-JO", "ar-AE", "ar-BH", "ar-DZ", "ar-SA", "ar-IQ", "ar-KW", "ar-MA", "ar-TN", "ar-OM", "ar-PS", "ar-QA", "ar-LB", "ar-EG", "fa-IR", "hi-IN", "th-TH", "ko-KR", "cmn-Hant-TW", "yue-Hant-HK", "ja-JP", "cmn-Hans-HK", "cmn-Hans-CN"]  # fmt: skip


def general_integration_settings(bi: BotIntegration, current_user: AppUser):
    if st.session_state.get(f"_bi_reset_{bi.id}"):
        st.session_state[f"_bi_streaming_enabled_{bi.id}"] = (
            BotIntegration._meta.get_field("streaming_enabled").default
        )
        st.session_state[f"_bi_show_feedback_buttons_{bi.id}"] = (
            BotIntegration._meta.get_field("show_feedback_buttons").default
        )
        st.session_state["analysis_urls"] = []
        st.session_state.pop("--list-view:analysis_urls", None)

    if bi.platform != Platform.TWILIO:
        bi.streaming_enabled = st.checkbox(
            "**📡 Streaming Enabled**",
            value=bi.streaming_enabled,
            key=f"_bi_streaming_enabled_{bi.id}",
        )
        st.caption("Responses will be streamed to the user in real-time if enabled.")
        bi.show_feedback_buttons = st.checkbox(
            "**👍🏾 👎🏽 Show Feedback Buttons**",
            value=bi.show_feedback_buttons,
            key=f"_bi_show_feedback_buttons_{bi.id}",
        )
        st.caption(
            "Users can rate and provide feedback on every copilot response if enabled."
        )

    st.write(
        """
        ##### 🧠 Analysis Scripts
        Analyze each incoming message and the copilot's response using a Gooey.AI /LLM workflow. Must return a JSON object.
        [Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/conversation-analysis).
        """
    )
    if "analysis_urls" not in st.session_state:
        st.session_state["analysis_urls"] = [
            (anal.published_run or anal.saved_run).get_app_url()
            for anal in bi.analysis_runs.all()
        ]

    if st.session_state.get("analysis_urls"):
        from recipes.VideoBots import VideoBotsPage

        st.anchor(
            "📊 View Results",
            str(
                furl(
                    VideoBotsPage.current_app_url(
                        RecipeTabs.integrations,
                        path_params=dict(integration_id=bi.api_integration_id()),
                    )
                )
                / "analysis/"
            ),
        )

    input_analysis_runs = []

    def render_workflow_url_input(key: str, del_key: str | None, d: dict):
        with st.columns([3, 2])[0]:
            ret = workflow_url_input(
                page_cls=CompareLLMPage,
                key=key,
                internal_state=d,
                del_key=del_key,
                current_user=current_user,
            )
            if not ret:
                return
            page_cls, sr, pr = ret
            if pr and pr.saved_run_id == sr.id:
                input_analysis_runs.append(dict(saved_run=None, published_run=pr))
            else:
                input_analysis_runs.append(dict(saved_run=sr, published_run=None))

    list_view_editor(
        add_btn_label="➕ Add",
        key="analysis_urls",
        render_inputs=render_workflow_url_input,
        flatten_dict_key="url",
    )

    with st.center():
        with st.div():
            pressed_update = st.button("✅ Save")
            pressed_reset = st.button(
                "Reset", key=f"_bi_reset_{bi.id}", type="tertiary"
            )
    if pressed_update or pressed_reset:
        with transaction.atomic():
            try:
                bi.full_clean()
                bi.save()
                # save analysis runs
                input_analysis_runs = [
                    BotIntegrationAnalysisRun.objects.get_or_create(
                        bot_integration=bi, **data
                    )[0].id
                    for data in input_analysis_runs
                ]
                # delete any analysis runs that were removed
                bi.analysis_runs.all().exclude(id__in=input_analysis_runs).delete()
            except ValidationError as e:
                st.error(str(e))
    st.write("---")


def twilio_specific_settings(bi: BotIntegration):
    SETTINGS_FIELDS = ["twilio_use_missed_call", "twilio_initial_text", "twilio_initial_audio_url", "twilio_waiting_text", "twilio_waiting_audio_url", "twilio_tts_voice", "twilio_asr_language"]  # fmt:skip
    if st.session_state.get(f"_bi_reset_{bi.id}"):
        for field in SETTINGS_FIELDS:
            st.session_state[f"_bi_{field}_{bi.id}"] = BotIntegration._meta.get_field(
                field
            ).default

    bi.twilio_tts_voice = (
        st.selectbox(
            "##### 🗣️ Twilio Voice",
            options=TWILIO_SUPPORTED_VOICES,
            value=bi.twilio_tts_voice,
            format_func=lambda x: x.capitalize(),
            key=f"_bi_twilio_tts_voice_{bi.id}",
        )
        or "Woman"
    )
    st.caption("Used when the underlying run does not have a Gooey TTS model enabled.")
    bi.twilio_asr_language = (
        st.selectbox(
            "##### 🌐 Twilio ASR Language",
            options=TWILIO_ASR_SUPPORTED_LANGUAGES,
            key=f"_bi_twilio_asr_language_{bi.id}",
            format_func=lambda x: langcodes.Language.get(x).display_name(),
            value=bi.twilio_asr_language,
        )
        or "en-US"
    )
    st.caption("Used when the underlying run does not have a Gooey ASR model enabled.")
    bi.twilio_initial_text = st.text_area(
        "###### 📝 Initial Text (said at the beginning of each call)",
        value=bi.twilio_initial_text,
        key=f"_bi_twilio_initial_text_{bi.id}",
    )
    bi.twilio_initial_audio_url = (
        st.file_uploader(
            "###### 🔊 Initial Audio (played at the beginning of each call)",
            accept=["audio/*"],
            key=f"_bi_twilio_initial_audio_url_{bi.id}",
        )
        or ""
    )
    bi.twilio_waiting_audio_url = (
        st.file_uploader(
            "###### 🎵 Waiting Audio (played while waiting for a response -- Voice)",
            accept=["audio/*"],
            key=f"_bi_twilio_waiting_audio_url_{bi.id}",
        )
        or ""
    )
    bi.twilio_waiting_text = st.text_area(
        "###### 📝 Waiting Text (texted while waiting for a response -- SMS)",
        key=f"_bi_twilio_waiting_text_{bi.id}",
    )
    bi.twilio_use_missed_call = st.checkbox(
        "📞 Use Missed Call",
        value=bi.twilio_use_missed_call,
        key=f"_bi_twilio_use_missed_call_{bi.id}",
    )
    st.caption(
        "When enabled, immediately hangs up incoming calls and calls back the user so they don't incur charges (depending on their carrier/plan)."
    )


def slack_specific_settings(bi: BotIntegration, default_name: str):
    if st.session_state.get(f"_bi_reset_{bi.id}"):
        st.session_state[f"_bi_name_{bi.id}"] = default_name
        st.session_state[f"_bi_slack_read_receipt_msg_{bi.id}"] = (
            BotIntegration._meta.get_field("slack_read_receipt_msg").default
        )

    bi.slack_read_receipt_msg = st.text_input(
        """
            ##### ✅ Read Receipt
            This message is sent immediately after recieving a user message and replaced with the copilot's response once it's ready.
            (leave blank to disable)
            """,
        placeholder=bi.slack_read_receipt_msg,
        value=bi.slack_read_receipt_msg,
        key=f"_bi_slack_read_receipt_msg_{bi.id}",
    )
    bi.name = st.text_input(
        """
            ##### 🪪 Channel Specific Bot Name
            This is the name the bot will post as in this specific channel (to be displayed in Slack)
            """,
        placeholder=bi.name,
        value=bi.name,
        key=f"_bi_name_{bi.id}",
    )
    st.caption("Enable streaming messages to Slack in real-time.")


def broadcast_input(bi: BotIntegration):
    from bots.tasks import send_broadcast_msgs_chunked
    from recipes.VideoBots import VideoBotsPage

    key = f"__broadcast_msg_{bi.id}"
    api_docs_url = (
        furl(
            settings.API_BASE_URL,
            fragment_path=f"operation/{VideoBotsPage.slug_versions[0]}__broadcast",
        )
        / "docs"
    )
    text = st.text_area(
        f"""
        ###### Broadcast Message 📢
        Broadcast a message to all users of this integration using this bot account.  \\
        You can also do this via the [API]({api_docs_url}) which allows filtering by phone number and more!
        """,
        key=key + ":text",
        placeholder="Type your message here...",
    )
    audio = st.file_uploader(
        "**🎤 Audio**",
        key=key + ":audio",
        help="Attach a video to this message.",
        optional=True,
        accept=["audio/*"],
    )
    video = None
    documents = None
    medium = "Voice Call"
    if bi.platform == Platform.TWILIO:
        medium = st.selectbox(
            "###### 📱 Medium",
            ["Voice Call", "SMS/MMS"],
            key=key + ":medium",
        )
    else:
        video = st.file_uploader(
            "**🎥 Video**",
            key=key + ":video",
            help="Attach a video to this message.",
            optional=True,
            accept=["video/*"],
        )
        documents = st.file_uploader(
            "**📄 Documents**",
            key=key + ":documents",
            help="Attach documents to this message.",
            accept_multiple_files=True,
            optional=True,
        )

    should_confirm_key = key + ":should_confirm"
    confirmed_send_btn = key + ":confirmed_send"
    if st.button("📤 Send Broadcast", style=dict(height="3.2rem"), key=key + ":send"):
        st.session_state[should_confirm_key] = True
    if not st.session_state.get(should_confirm_key):
        return

    convos = bi.conversations.all()
    if st.session_state.get(confirmed_send_btn):
        st.success("Started sending broadcast!")
        st.session_state.pop(confirmed_send_btn)
        st.session_state.pop(should_confirm_key)
        send_broadcast_msgs_chunked(
            text=text,
            audio=audio,
            video=video,
            documents=documents,
            bi=bi,
            convo_qs=convos,
            medium=medium,
        )
    else:
        if not convos.exists():
            st.error("No users have interacted with this bot yet.", icon="⚠️")
            return
        st.write(
            f"Are you sure? This will send a message to all {convos.count()} users that have ever interacted with this bot.\n"
        )
        st.button("✅ Yes, Send", key=confirmed_send_btn)


def get_bot_test_link(bi: BotIntegration) -> str | None:
    if bi.wa_phone_number:
        return (
            furl("https://wa.me/", query_params={"text": "Hi"})
            / bi.wa_phone_number.as_e164
        ).tostr()
    elif bi.slack_team_id:
        return (
            furl("https://app.slack.com/client")
            / bi.slack_team_id
            / bi.slack_channel_id
        ).tostr()
    elif bi.ig_username:
        return (furl("http://instagram.com/") / bi.ig_username).tostr()
    elif bi.fb_page_name:
        return (furl("https://www.facebook.com/") / bi.fb_page_id).tostr()
    elif bi.platform == Platform.WEB:
        return get_app_route_url(
            chat_route,
            path_params=dict(
                integration_id=bi.api_integration_id(),
                integration_name=slugify(bi.name) or "untitled",
            ),
        )
    elif bi.twilio_phone_number_sid:
        return f"https://console.twilio.com/us1/develop/phone-numbers/manage/incoming/{bi.twilio_phone_number_sid}/calls"
    else:
        return None


def get_web_widget_embed_code(bi: BotIntegration) -> str:
    lib_src = get_app_route_url(
        chat_lib_route,
        path_params=dict(
            integration_id=bi.api_integration_id(),
            integration_name=slugify(bi.name) or "untitled",
        ),
    )
    return dedent(
        f"""
        <div id="gooey-embed"></div>
        <script async defer onload="GooeyEmbed.mount()" src="{lib_src}"></script>
        """
    ).strip()


def web_widget_config(bi: BotIntegration, user: AppUser | None):
    with st.div(style={"width": "100%", "textAlign": "left"}):
        col1, col2 = st.columns(2)
    with col1:
        if st.session_state.get("--update-display-picture"):
            display_pic = st.file_uploader(
                label="###### Display Picture",
                accept=["image/*"],
            )
            if display_pic:
                bi.photo_url = display_pic
        else:
            if st.button(f"{icons.camera} Change Photo"):
                st.session_state["--update-display-picture"] = True
                st.experimental_rerun()
        bi.name = st.text_input("###### Name", value=bi.name)
        bi.descripton = st.text_area(
            "###### Description",
            value=bi.descripton,
        )
        scol1, scol2 = st.columns(2)
        with scol1:
            bi.by_line = st.text_input(
                "###### By Line",
                value=bi.by_line or (user and f"By {user.display_name}"),
            )
        with scol2:
            bi.website_url = st.text_input(
                "###### Website Link",
                value=bi.website_url or (user and user.website_url),
            )

        st.write("###### Conversation Starters")
        bi.conversation_starters = list(
            filter(
                None,
                [
                    st.text_input("", key=f"--question-{i}", value=value)
                    for i, value in zip_longest(range(4), bi.conversation_starters)
                ],
            )
        )

        config = (
            dict(
                mode="inline",
                showSources=True,
                enablePhotoUpload=False,
                enableLipsyncVideo=False,
                enableAudioMessage=True,
                branding=(
                    dict(showPoweredByGooey=True)
                    | bi.web_config_extras.get("branding", {})
                ),
            )
            | bi.web_config_extras
        )

        scol1, scol2 = st.columns(2)
        with scol1:
            config["showSources"] = st.checkbox(
                "Show Sources", value=config["showSources"]
            )
            config["enablePhotoUpload"] = st.checkbox(
                "Allow Photo Upload", value=config["enablePhotoUpload"]
            )
        with scol2:
            config["enableAudioMessage"] = st.checkbox(
                "Enable Audio Message", value=config["enableAudioMessage"]
            )
            config["enableLipsyncVideo"] = st.checkbox(
                "Enable Lipsync Video", value=config["enableLipsyncVideo"]
            )
            # config["branding"]["showPoweredByGooey"] = st.checkbox(
            #     "Show Powered By Gooey", value=config["branding"]["showPoweredByGooey"]
            # )

        with st.expander("Embed Settings"):
            st.caption(
                "These settings will take effect when you embed the widget on your website."
            )
            scol1, scol2 = st.columns(2)
            with scol1:
                config["mode"] = st.selectbox(
                    "###### Mode",
                    ["popup", "inline", "fullscreen"],
                    value=config["mode"],
                    format_func=lambda x: x.capitalize(),
                )
                if config["mode"] == "popup":
                    config["branding"]["fabLabel"] = st.text_input(
                        "###### Label",
                        value=config["branding"].get("fabLabel", "Help"),
                    )
                else:
                    config["branding"].pop("fabLabel", None)

        # remove defaults
        bi.web_config_extras = config

        with st.div(className="d-flex justify-content-end"):
            if st.button(
                f"{icons.save} Update Web Preview",
                type="primary",
                className="align-right",
            ):
                bi.save()
                st.experimental_rerun()
    with col2:
        with st.center(), st.div():
            web_preview_tab = f"{icons.chat} Web Preview"
            api_tab = f"{icons.api} API"
            selected = st.horizontal_radio("", [web_preview_tab, api_tab])
        if selected == web_preview_tab:
            st.html(
                # language=html
                f"""
                <div id="gooey-embed" style="border: 1px solid #eee; height: 80vh"></div>
                <script id="gooey-embed-script" src="{settings.WEB_WIDGET_LIB}"></script>
                """
            )
            st.js(
                # language=javascript
                """
                async function loadGooeyEmbed() {
                    await window.waitUntilHydrated;
                    if (typeof GooeyEmbed === 'undefined') return;
                    GooeyEmbed.unmount();
                    GooeyEmbed.mount(config);
                }
                const script = document.getElementById("gooey-embed-script");
                if (script) script.onload = loadGooeyEmbed;
                loadGooeyEmbed();
                """,
                config=bi.get_web_widget_config() | dict(mode="inline"),
            )
        else:
            bot_api_example_generator(bi.api_integration_id())
