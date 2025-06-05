import json
import math
import typing
from itertools import zip_longest
import typing_extensions

import gooey_gui as gui
from django.db.models import Q, QuerySet
from furl import furl
from pydantic import BaseModel, Field

from bots.models import (
    BotIntegration,
    Platform,
    PublishedRun,
    SavedRun,
    Workflow,
    WorkflowAccessLevel,
)
from celeryapp.tasks import send_integration_attempt_email
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import icons, settings
from daras_ai_v2.asr import (
    AsrModels,
    TranslationModels,
    asr_language_selector,
    asr_model_selector,
    language_filter_selector,
    run_asr,
    run_translate,
    should_translate_lang,
    translation_language_selector,
    translation_model_selector,
)
from daras_ai_v2.azure_doc_extract import (
    azure_form_recognizer,
    azure_form_recognizer_models,
)
from daras_ai_v2.base import BasePage, RecipeRunState, RecipeTabs, StateKeys
from daras_ai_v2.bot_integration_connect import connect_bot_to_published_run
from daras_ai_v2.bot_integration_widgets import (
    broadcast_input,
    general_integration_settings,
    integrations_welcome_screen,
    web_widget_config,
)
from daras_ai_v2.csv_lines import csv_decode_row
from daras_ai_v2.doc_search_settings_widgets import (
    SUPPORTED_SPREADSHEET_TYPES,
    bulk_documents_uploader,
    cache_knowledge_widget,
    citation_style_selector,
    doc_extract_selector,
    doc_search_advanced_settings,
    keyword_instructions_widget,
    query_instructions_widget,
)
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.field_render import field_desc, field_title, field_title_desc
from daras_ai_v2.functional import flatapply_parallel
from daras_ai_v2.glossary import validate_glossary_document
from daras_ai_v2.language_filters import asr_languages_without_dialects
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_SYSTEM,
    CHATML_ROLE_USER,
    SUPERSCRIPT,
    ConversationEntry,
    LargeLanguageModels,
    calc_gpt_tokens,
    format_chat_entry,
    get_entry_images,
    get_entry_text,
    run_language_model,
)
from daras_ai_v2.language_model_settings_widgets import (
    LanguageModelSettings,
    language_model_selector,
    language_model_settings,
)
from daras_ai_v2.lipsync_api import LipsyncModel, LipsyncSettings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import OptionalHttpUrlStr, HttpUrlStr
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.search_ref import (
    CitationStyles,
    apply_response_formattings_prefix,
    apply_response_formattings_suffix,
    parse_refs,
)
from daras_ai_v2.text_output_widget import text_output
from daras_ai_v2.text_to_speech_settings_widgets import (
    TextToSpeechProviders,
    elevenlabs_load_state,
    text_to_speech_provider_selector,
    text_to_speech_settings,
)
from daras_ai_v2.variables_widget import render_prompt_vars
from daras_ai_v2.vector_search import (
    DocSearchRequest,
    doc_or_yt_url_to_file_metas,
    doc_url_to_text_pages,
)
from functions.models import FunctionTrigger
from functions.recipe_functions import (
    LLMTool,
    get_tools_from_state,
    render_called_functions,
)
from recipes.DocSearch import get_top_k_references, references_as_prompt
from recipes.GoogleGPT import SearchReference
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage, TextToSpeechSettings
from url_shortener.models import ShortenedURL
from widgets.demo_button import render_demo_buttons_header

if typing.TYPE_CHECKING:
    pass


GRAYCOLOR = "#00000073"
DEFAULT_TRANSLATION_MODEL = TranslationModels.google.name

SAFETY_BUFFER = 100


class ReplyButton(typing_extensions.TypedDict):
    id: str
    title: str


class VideoBotsPage(BasePage):
    PROFIT_CREDITS = 3

    title = "Copilot for your Enterprise"  # "Create Interactive Video Bots"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/8c014530-88d4-11ee-aac9-02420a00016b/Copilot.png.png"
    workflow = Workflow.VIDEO_BOTS
    slug_versions = ["video-bots", "bots", "copilot"]

    functions_in_settings = False

    sane_defaults = {
        "messages": [],
        # tts
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.name,
        "google_voice_name": "en-IN-Wavenet-A",
        "google_pitch": 0.0,
        "google_speaking_rate": 1.0,
        "uberduck_voice_name": "Aiden Botha",
        "uberduck_speaking_rate": 1.0,
        "elevenlabs_model": "eleven_multilingual_v2",
        "elevenlabs_stability": 0.5,
        "elevenlabs_similarity_boost": 0.75,
        # gpt3
        "selected_model": LargeLanguageModels.text_davinci_003.name,
        "avoid_repetition": True,
        "num_outputs": 1,
        "quality": 1.0,
        "max_tokens": 1500,
        "sampling_temperature": 0.5,
        # wav2lip
        "face_padding_top": 0,
        "face_padding_bottom": 10,
        "face_padding_left": 0,
        "face_padding_right": 0,
        # doc search
        "citation_style": CitationStyles.number.name,
        "documents": [],
        "task_instructions": "Make sure to use only the following search results to guide your response. "
        'If the Search Results do not contain enough information, say "I don\'t know".',
        "query_instructions": "<Chat History> \n{{ messages }} \n\n<Last Message> \n{{ input_prompt }} \n\n<Instructions> \nGiven the conversation, only rephrase the last message to be a standalone statement in 2nd person's perspective. Make sure you include only the relevant parts of the conversation required to answer the follow-up question, and not the answer to the question. If the conversation is irrelevant to the current question being asked, discard it. Don't use quotes in your response. \n\n<Query Sentence>",
        "max_references": 3,
        "max_context_words": 200,
        "scroll_jump": 5,
        "use_url_shortener": False,
        "dense_weight": 1.0,
        "translation_model": DEFAULT_TRANSLATION_MODEL,
    }

    class RequestModelBase(BasePage.RequestModel):
        input_prompt: str | None = None
        input_audio: str | None = None
        input_images: list[HttpUrlStr] | None = None
        input_documents: list[HttpUrlStr] | None = None

        doc_extract_url: str | None = Field(
            None,
            title="📚 Document Extract Workflow",
            description="Select a workflow to extract text from documents and images.",
        )

        # conversation history/context
        messages: list[dict] | None = None

        bot_script: str | None = None

        # llm model
        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        ) = None
        document_model: str | None = Field(
            None,
            title="🩻 Photo / Document Intelligence",
            description="When your copilot users upload a photo or pdf, what kind of document are they mostly likely to upload? "
            "(via [Azure](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/use-sdk-rest-api?view=doc-intel-3.1.0&tabs=linux&pivots=programming-language-rest-api))",
        )

        # doc search
        task_instructions: str | None = None
        query_instructions: str | None = None
        keyword_instructions: str | None = None
        documents: list[HttpUrlStr] | None = None
        max_references: int | None = None
        max_context_words: int | None = None
        scroll_jump: int | None = None

        embedding_model: (
            typing.Literal[tuple(e.name for e in EmbeddingModels)] | None
        ) = None
        dense_weight: float | None = DocSearchRequest.model_fields["dense_weight"]

        citation_style: typing.Literal[tuple(e.name for e in CitationStyles)] | None = (
            None
        )
        use_url_shortener: bool | None = None
        check_document_updates: bool | None = None

        asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None = Field(
            None,
            title="Speech-to-Text Provider",
            description="Choose a model to transcribe incoming audio messages to text.",
        )
        asr_language: str | None = Field(
            None,
            title="Spoken Language",
            description="Choose a language to transcribe incoming audio messages to text.",
        )
        asr_task: typing.Literal["translate", "transcribe"] | None = Field(
            None,
            title="ASR Model Task",
            description="Use **{asr_model}** for speech translation from **{asr_language}** to **English**",
        )
        asr_prompt: str | None = Field(
            None,
            title="👩‍💻 Prompt",
            description="Optional prompt that the model can use as context to better understand the speech and maintain a consistent writing style.",
        )

        translation_model: (
            typing.Literal[tuple(e.name for e in TranslationModels)] | None
        ) = None
        user_language: str | None = Field(
            None,
            title="Translation Language",
            description="Choose a language to translate incoming text & audio messages to English and responses back to your selected language. Useful for low-resource languages.",
        )
        # llm_language: str | None = "en" <-- implicit since this is hardcoded everywhere in the code base (from facebook and bots to slack and copilot etc.)
        input_glossary_document: OptionalHttpUrlStr = Field(
            None,
            title="Input Glossary",
            description="""
Translation Glossary for User Langauge -> LLM Language (English)
            """,
        )
        output_glossary_document: OptionalHttpUrlStr = Field(
            None,
            title="Output Glossary",
            description="""
Translation Glossary for LLM Language (English) -> User Langauge
            """,
        )

        lipsync_model: typing.Literal[tuple(e.name for e in LipsyncModel)] = (
            LipsyncModel.Wav2Lip.name
        )

        tools: list[str] | None = Field(
            None,
            title="🛠️ Tools",
            description="Use `functions` instead.",
            deprecated=True,
        )

    class RequestModel(
        LipsyncSettings, TextToSpeechSettings, LanguageModelSettings, RequestModelBase
    ):
        pass

    class ResponseModel(BaseModel):
        final_prompt: str | list[ConversationEntry] = []

        output_text: list[str] = []
        output_audio: list[HttpUrlStr] = []
        output_video: list[HttpUrlStr] = []

        # intermediate text
        raw_input_text: str | None = None
        raw_tts_text: list[str] | None = None
        raw_output_text: list[str] | None = None

        # doc search
        references: list[SearchReference] | None = []
        final_search_query: str | None = None
        final_keyword_query: str | list[str] | None = None

        # function calls
        output_documents: list[HttpUrlStr] | None = None
        reply_buttons: list[ReplyButton] | None = None

        finish_reason: list[str] | None = None

    def related_workflows(self):
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.DeforumSD import DeforumSDPage
        from recipes.DocSearch import DocSearchPage
        from recipes.LipsyncTTS import LipsyncTTSPage

        return [
            LipsyncTTSPage,
            DocSearchPage,
            DeforumSDPage,
            CompareText2ImgPage,
        ]

    @classmethod
    def get_run_title(cls, sr: SavedRun, pr: PublishedRun | None) -> str:
        import langcodes

        if pr and pr.title and not pr.is_root():
            return pr.title

        try:
            lang = langcodes.Language.get(
                sr.state.get("user_language") or sr.state.get("asr_language") or ""
            ).display_name()
        except (KeyError, langcodes.LanguageTagError):
            lang = None

        return " ".join(filter(None, [lang, cls.get_recipe_title()]))

    @classmethod
    def get_prompt_title(cls, state: dict) -> str | None:
        # don't show the input prompt in the run titles, instead show get_run_title()
        return None

    def render_description(self):
        gui.write(
            """
Have you ever wanted to create a bot that you could talk to about anything? Ever wanted to create your own https://dara.network/RadBots or https://Farmer.CHAT? This is how.

This workflow takes a dialog LLM prompt describing your character, a collection of docs & links and optional an video clip of your bot's face and  voice settings.

We use all these to build a bot that anyone can speak to about anything and you can host directly in your own site or app, or simply connect to your Facebook, WhatsApp or Instagram page.

How It Works:
1. Appends the user's question to the bottom of your dialog script.
2. Sends the appended script to OpenAI's GPT3 asking it to respond to the question in the style of your character
3. Synthesizes your character's response as audio using your voice settings (using Google Text-To-Speech or Uberduck)
4. Lip syncs the face video clip to the voice clip
5. Shows the resulting video to the user

PS. This is the workflow that we used to create RadBots - a collection of Turing-test videobots, authored by leading international writers, singers and playwrights - and really inspired us to create Gooey.AI so that every person and organization could create their own fantastic characters, in any personality of their choosing. It's also the workflow that powers https://Farmer.CHAT and was demo'd at the UN General Assembly in April 2023 as a multi-lingual WhatsApp bot for Indian, Ethiopian and Kenyan farmers.
        """
        )

    def render_form_v2(self):
        gui.text_area(
            """
            #### <i class="fa-regular fa-lightbulb" style="fontSize:20px"></i> Instructions
            """,
            key="bot_script",
            height=300,
            help="[Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/craft-your-ai-copilots-personality) about how to prompt your copilot's personality!",
        )

        language_model_selector(
            label=""" #### <i class="fa-sharp fa-regular fa-brain-circuit" style="fontSize:20px"></i> Language Model """
        )

        bulk_documents_uploader(
            """ 
            #### <i class="fa-light fa-books" style="fontSize:20px"></i> Knowledge
            """,
            accept=["audio/*", "application/*", "video/*", "text/*"],
            help="Add documents or links to give your copilot a knowledge base. When asked a question, we'll search them to generate an answer with citations. [Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/curate-your-knowledge-base-documents)",
        )

        gui.markdown("#### 💪 Capabilities")

        if gui.switch(
            "##### 🦻 Speech Recognition & Translation",
            value=bool(
                gui.session_state.get("user_language")
                or gui.session_state.get("asr_model")
            ),
        ):
            with gui.div(className="pt-2 ps-1"):
                gui.caption(field_desc(self.RequestModel, "user_language"))

                # drop down to filter models based on the selected language
                selected_filter_language = language_filter_selector(
                    options=asr_languages_without_dialects()
                )

                col1, col2 = gui.columns(2, responsive=False)
                with col1:
                    asr_model = asr_model_selector(
                        key="asr_model",
                        language_filter=selected_filter_language,
                        label=f"###### {field_title(self.RequestModel, 'asr_model')}",
                        format_func=lambda x: (
                            AsrModels[x].value if x else "Auto Select"
                        ),
                    )
                with col2:
                    if asr_model:
                        asr_language = asr_language_selector(
                            asr_model,
                            language_filter=selected_filter_language,
                            label=f"###### {field_title(self.RequestModel, 'asr_language')}",
                            key="asr_language",
                        )
                    else:
                        asr_language = None

                if asr_model.supports_input_prompt():
                    gui.text_area(
                        f"###### {field_title_desc(self.RequestModel, 'asr_prompt')}",
                        key="asr_prompt",
                        value="Transcribe the recording as accurately as possible.",
                        height=300,
                    )

                gui.newline()
                if gui.checkbox(
                    "🔠 **Translate to & from English**",
                    value=bool(gui.session_state.get("translation_model")),
                ):
                    gui.caption(
                        "Choose an AI model & language to translate incoming text & audio messages to English and responses back your selected language. Useful for low-resource languages."
                    )

                    if asr_model and asr_model.supports_speech_translation():
                        with gui.div(className="text-muted"):
                            if gui.checkbox(
                                label=field_desc(self.RequestModel, "asr_task").format(
                                    asr_model=asr_model.value,
                                    asr_language=asr_language or "Detected Language",
                                ),
                                value=gui.session_state.get("asr_task") == "translate",
                            ):
                                gui.session_state["asr_task"] = "translate"
                            else:
                                gui.session_state.pop("asr_task", None)
                    else:
                        gui.session_state.pop("asr_task", None)

                    col1, col2 = gui.columns(2)
                    with col1:
                        translation_model = translation_model_selector(
                            allow_none=False,
                            language_filter=selected_filter_language,
                        )
                    with col2:
                        translation_language_selector(
                            model=translation_model,
                            language_filter=selected_filter_language,
                            label=f"###### {field_title(self.RequestModel, 'user_language')}",
                            key="user_language",
                        )
                else:
                    gui.session_state["asr_task"] = None
                    gui.session_state["translation_model"] = None
                    gui.session_state["user_language"] = None

                gui.newline()
        else:
            gui.session_state["asr_model"] = None
            gui.session_state["asr_language"] = None
            gui.session_state["asr_prompt"] = None

            gui.session_state["asr_task"] = None
            gui.session_state["translation_model"] = None
            gui.session_state["user_language"] = None

        if gui.switch(
            "##### 🗣️ Text to Speech & Lipsync",
            value=bool(gui.session_state.get("tts_provider")),
        ):
            with gui.div(className="pt-2 ps-1"):
                text_to_speech_provider_selector(self)

            gui.newline()

            enable_video = gui.switch(
                "##### 🫦 Add Lipsync Video",
                value=bool(gui.session_state.get("input_face")),
            )
        else:
            gui.session_state["tts_provider"] = None
            enable_video = False
        if enable_video:
            with gui.div(className="pt-2 ps-1"):
                gui.file_uploader(
                    """
                    ###### 👩‍🦰 Input Face
                    Upload a video/image with one human face. mp4, mov, png, jpg or gif preferred.
                    """,
                    key="input_face",
                )
                enum_selector(
                    LipsyncModel,
                    label="###### Lipsync Model",
                    key="lipsync_model",
                    use_selectbox=True,
                )
            gui.newline()
        else:
            gui.session_state["input_face"] = None
            gui.session_state.pop("lipsync_model", None)

        if gui.switch(
            "##### 🩻 Photo & Document Intelligence",
            value=bool(gui.session_state.get("document_model")),
        ):
            with gui.div(className="pt-2 ps-1"):
                if settings.AZURE_FORM_RECOGNIZER_KEY:
                    doc_model_descriptions = azure_form_recognizer_models()
                else:
                    doc_model_descriptions = {}
                gui.selectbox(
                    f"{field_desc(self.RequestModel, 'document_model')}",
                    key="document_model",
                    options=doc_model_descriptions,
                    format_func=lambda x: f"{doc_model_descriptions[x]} ({x})",
                )
            gui.newline()
        else:
            gui.session_state["document_model"] = None

    def validate_form_v2(self):
        input_glossary = gui.session_state.get("input_glossary_document", "")
        output_glossary = gui.session_state.get("output_glossary_document", "")
        if input_glossary:
            validate_glossary_document(input_glossary)
        if output_glossary:
            validate_glossary_document(output_glossary)

    def render_usage_guide(self):
        youtube_video("-j2su1r8pEg")

    def render_settings(self):
        tts_provider = gui.session_state.get("tts_provider")
        if tts_provider:
            text_to_speech_settings(self, tts_provider)
            gui.write("---")

        lipsync_model = gui.session_state.get("lipsync_model")
        if lipsync_model:
            lipsync_settings(lipsync_model)
            gui.write("---")

        translation_model = gui.session_state.get(
            "translation_model", DEFAULT_TRANSLATION_MODEL
        )
        if (
            gui.session_state.get("user_language")
            and TranslationModels[translation_model].supports_glossary
        ):
            gui.markdown("##### 🔠 Translation Settings")
            enable_glossary = gui.checkbox(
                "📖 Add Glossary",
                value=bool(
                    gui.session_state.get("input_glossary_document")
                    or gui.session_state.get("output_glossary_document")
                ),
                help="[Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/advanced-settings#fine-tuned-language-understanding-with-custom-glossaries) about how to super-charge your copilots domain specific language understanding!",
            )
            if enable_glossary:
                gui.caption(
                    """
                    Provide a glossary to customize translation and improve accuracy of domain-specific terms.
                    If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing).
                    """
                )
                gui.file_uploader(
                    f"##### {field_title_desc(self.RequestModel, 'input_glossary_document')}",
                    key="input_glossary_document",
                    accept=SUPPORTED_SPREADSHEET_TYPES,
                )
                gui.file_uploader(
                    f"##### {field_title_desc(self.RequestModel, 'output_glossary_document')}",
                    key="output_glossary_document",
                    accept=SUPPORTED_SPREADSHEET_TYPES,
                )
            else:
                gui.session_state["input_glossary_document"] = None
                gui.session_state["output_glossary_document"] = None
            gui.write("---")

        documents = gui.session_state.get("documents")
        if documents:
            gui.write("#### 📄 Knowledge Base")
            gui.text_area(
                """
            ###### 👩‍🏫 Search Instructions
            How should the LLM interpret the results from your knowledge base?
            """,
                key="task_instructions",
                height=300,
            )

            citation_style_selector()
            gui.checkbox("🔗 Shorten citation links", key="use_url_shortener")
            cache_knowledge_widget(self)
            doc_extract_selector(self.request.user)

            gui.write("---")

        gui.markdown(
            """
            #### Advanced Settings
            In general, you should not need to adjust these.
            """
        )

        if documents:
            query_instructions_widget()
            keyword_instructions_widget()
            gui.write("---")
            doc_search_advanced_settings()
            gui.write("---")

        gui.write("##### 🔠 Language Model Settings")
        language_model_settings(gui.session_state.get("selected_model"))

    def run_as_api_tab(self):
        elevenlabs_load_state(self)
        super().run_as_api_tab()

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["input_prompt", "messages"]

    def render_run_preview_output(self, state: dict):
        input_prompt = state.get("input_prompt")
        if input_prompt:
            gui.write(
                "**Prompt**\n```properties\n"
                + truncate_text_words(input_prompt, maxlen=200)
                + "\n```"
            )

        gui.write("**Response**")

        output_video = state.get("output_video")
        if output_video:
            gui.video(output_video[0], autoplay=True)

        output_text = state.get("output_text")
        if output_text:
            gui.write(output_text[0], line_clamp=5)

    scroll_into_view = False

    def _render_running_output(self):
        ## The embedded web widget includes a running output, so just scroll it into view

        # language=JavaScript
        gui.js(
            """document.querySelector("#gooey-embed")?.scrollIntoView({ behavior: "smooth", block: "start" })"""
        )

    def render_output(self):
        from daras_ai_v2.bots import parse_bot_html

        gui.tag(
            "button",
            type="submit",
            name="onSendMessage",
            hidden=True,
            id="onSendMessage",
        )
        input_payload = gui.session_state.pop("onSendMessage", None)
        if input_payload:
            try:
                input_data = json.loads(input_payload)
            except (json.JSONDecodeError, TypeError):
                pass
            else:
                self.on_send(
                    input_data.get("input_prompt"),
                    input_data.get("input_images"),
                    input_data.get("input_audio"),
                    input_data.get("input_documents"),
                    input_data.get("button_pressed"),
                    input_data.get("input_location"),
                )

        gui.tag(
            "button",
            type="submit",
            name="onNewConversation",
            value="yes",
            hidden=True,
            id="onNewConversation",
        )
        if gui.session_state.pop("onNewConversation", None):
            gui.session_state["messages"] = []
            gui.session_state["input_prompt"] = ""
            gui.session_state["input_images"] = None
            gui.session_state["input_audio"] = None
            gui.session_state["input_documents"] = None
            gui.session_state["raw_input_text"] = ""
            self.clear_outputs()
            gui.session_state["final_keyword_query"] = ""
            gui.session_state["final_search_query"] = ""
            gui.rerun()

        entries = gui.session_state.get("messages", []).copy()
        messages = []  # chat widget internal mishmash format
        for entry in entries:
            role = entry.get("role")
            if role == CHATML_ROLE_USER:
                messages.append(
                    dict(
                        role=role,
                        input_prompt=get_entry_text(entry),
                        input_images=get_entry_images(entry) or [],
                    )
                )
            elif role == CHATML_ROLE_ASSISTANT:
                messages.append(
                    dict(
                        role=role,
                        type="final_response",
                        status="completed",
                        output_text=[parse_bot_html(get_entry_text(entry))[1]],
                    )
                )

        # add last input to history if present
        show_raw_msgs = False
        if show_raw_msgs:
            input_prompt = gui.session_state.get("raw_input_text") or ""
        else:
            input_prompt = gui.session_state.get("input_prompt") or ""
        input_images = gui.session_state.get("input_images") or []
        input_audio = gui.session_state.get("input_audio") or ""
        input_documents = gui.session_state.get("input_documents") or []
        if input_prompt or input_images or input_audio or input_documents:
            messages.append(
                dict(
                    role=CHATML_ROLE_USER,
                    input_prompt=input_prompt,
                    input_images=input_images,
                    input_audio=input_audio,
                    input_documents=input_documents,
                ),
            )

            # add last output
            run_status = self.get_run_state(gui.session_state)
            if run_status == RecipeRunState.running:
                event_type = "message_part"
            elif run_status == RecipeRunState.failed:
                event_type = "error"
            else:
                event_type = "final_response"
            raw_output_text = gui.session_state.get("raw_output_text") or []
            output_text = gui.session_state.get("output_text") or []
            output_video = gui.session_state.get("output_video") or []
            output_audio = gui.session_state.get("output_audio") or []
            text = output_text and output_text[0] or ""
            if text:
                buttons, text, disable_feedback = parse_bot_html(text)
            else:
                buttons = []
            messages.append(
                dict(
                    role=CHATML_ROLE_ASSISTANT,
                    type=event_type,
                    status=run_status,
                    detail=gui.session_state.get(StateKeys.run_status) or "",
                    raw_output_text=raw_output_text,
                    output_text=[text],
                    text=text,
                    output_video=output_video,
                    output_audio=output_audio,
                    references=gui.session_state.get("references") or [],
                    buttons=buttons,
                )
            )

        gui.html(
            # language=html
            f"""
<div id="gooey-embed" className="border rounded py-1 mb-3 bg-white" style="height: 98vh"></div>
<script id="gooey-embed-script" src="{settings.WEB_WIDGET_LIB}"></script>
            """
        )
        gui.js(
            # language=javascript
            """
async function loadGooeyEmbed() {
    await window.waitUntilHydrated;
    if (typeof GooeyEmbed === "undefined" ||
        document.getElementById("gooey-embed")?.children.length
    )
        return;
    let controller = {
        messages,
        onSendMessage: (payload) => {
            let btn = document.getElementById("onSendMessage");
            if (!btn) return;
            btn.value = JSON.stringify(payload);
            btn.click();
        },
        onNewConversation() {
          document.getElementById("onNewConversation").click();
        },
    };
    GooeyEmbed.controller = controller;
    GooeyEmbed.mount(config, controller);
}

const script = document.getElementById("gooey-embed-script");
if (script) script.onload = loadGooeyEmbed;
loadGooeyEmbed();
window.addEventListener("hydrated", loadGooeyEmbed);

if (typeof GooeyEmbed !== "undefined" && GooeyEmbed.controller) {
    GooeyEmbed.controller.setMessages?.(messages);
    console.log("setMessages:", messages);
}
            """,
            config=dict(
                integration_id="magic",
                target="#gooey-embed",
                mode="inline",
                enableAudioMessage=True,
                enablePhotoUpload=True,
                enableConversations=False,
                branding=dict(
                    name=self.current_pr.title,
                    photoUrl=self.current_pr.photo_url,
                    title="Preview",
                    showPoweredByGooey=False,
                ),
                fillParent=True,
                secrets=dict(GOOGLE_MAPS_API_KEY=settings.GOOGLE_MAPS_API_KEY),
            ),
            messages=messages,
        )

        render_called_functions(saved_run=self.current_sr, trigger=FunctionTrigger.pre)
        render_called_functions(
            saved_run=self.current_sr, trigger=FunctionTrigger.prompt
        )
        render_called_functions(saved_run=self.current_sr, trigger=FunctionTrigger.post)

    def _render_regenerate_button(self):
        pass
    
    def on_send(
        self,
        new_input_prompt: str | None,
        new_input_images: list[str] | None,
        new_input_audio: str | None,
        new_input_documents: list[str] | None,
        button_pressed: list[str] | None,
        input_location: dict[str, float] | None,
    ):
        if button_pressed:
            # encoded by parse_html
            target, title = None, None
            parts = csv_decode_row(button_pressed.get("button_id", ""))
            if len(parts) >= 3:
                target = parts[1]
                title = parts[-1]
            value = title or button_pressed.get("button_title", "")
            if target and target != "input_prompt":
                gui.session_state[target] = value
            else:
                new_input_prompt = value

        if input_location:
            from daras_ai_v2.bots import handle_location_msg

            new_input_prompt = handle_location_msg(input_location)

        prev_input = gui.session_state.get("raw_input_text") or ""
        prev_output = (gui.session_state.get("raw_output_text") or [""])[0]
        prev_input_images = gui.session_state.get("input_images")
        prev_input_audio = gui.session_state.get("input_audio")
        prev_input_documents = gui.session_state.get("input_documents")

        if (
            prev_input or prev_input_images or prev_input_audio or prev_input_documents
        ) and prev_output:
            # append previous input to the history
            gui.session_state["messages"] = gui.session_state.get("messages", []) + [
                format_chat_entry(
                    role=CHATML_ROLE_USER,
                    content_text=prev_input,
                    input_images=prev_input_images,
                    input_audio=prev_input_audio,
                    input_documents=prev_input_documents,
                ),
                format_chat_entry(
                    role=CHATML_ROLE_ASSISTANT,
                    content_text=prev_output,
                ),
            ]

        # add new input to the state
        gui.session_state["input_prompt"] = new_input_prompt
        gui.session_state["input_audio"] = new_input_audio or None
        gui.session_state["input_images"] = new_input_images or None
        gui.session_state["input_documents"] = new_input_documents or None

        self.submit_and_redirect()

    def render_steps(self):
        if gui.session_state.get("tts_provider"):
            gui.video(gui.session_state.get("input_face"), caption="Input Face")

        final_search_query = gui.session_state.get("final_search_query")
        if final_search_query:
            gui.text_area(
                "###### `final_search_query`", value=final_search_query, disabled=True
            )

        final_keyword_query = gui.session_state.get("final_keyword_query")
        if final_keyword_query:
            if isinstance(final_keyword_query, list):
                gui.write("###### `final_keyword_query`")
                gui.json(final_keyword_query)
            else:
                gui.text_area(
                    "###### `final_keyword_query`",
                    value=str(final_keyword_query),
                    disabled=True,
                )

        references = gui.session_state.get("references", [])
        if references:
            gui.write("###### `references`")
            gui.json(references, collapseStringsAfterLength=False)

        if gui.session_state.get("functions"):
            try:
                prompt_funcs = list(
                    get_tools_from_state(gui.session_state, FunctionTrigger.prompt)
                )
            except Exception:
                prompt_funcs = None
            if prompt_funcs:
                gui.write(f"🧩 `{FunctionTrigger.prompt.name} functions`")
                for tool in prompt_funcs:
                    gui.json(
                        tool.spec.get("function", tool.spec),
                        depth=3,
                        collapseStringsAfterLength=False,
                    )

        final_prompt = gui.session_state.get("final_prompt")
        if final_prompt:
            if isinstance(final_prompt, str):
                text_output("###### `final_prompt`", value=final_prompt, height=300)
            else:
                gui.write(
                    '###### <i class="fa-sharp fa-light fa-rectangle-terminal"></i> `final_prompt`',
                    unsafe_allow_html=True,
                )
                gui.json(final_prompt, depth=5)

        for k in ["raw_output_text", "output_text", "raw_tts_text"]:
            for idx, text in enumerate(gui.session_state.get(k) or []):
                gui.text_area(
                    f"###### 📜 `{k}[{idx}]`",
                    value=text,
                    disabled=True,
                )

        for idx, audio_url in enumerate(gui.session_state.get("output_audio", [])):
            gui.write(f"###### 🔉 `output_audio[{idx}]`")
            gui.audio(audio_url)

    def get_raw_price(self, state: dict):
        total = self.get_total_linked_usage_cost_in_credits() + self.PROFIT_CREDITS

        if state.get("tts_provider") == TextToSpeechProviders.ELEVEN_LABS.name:
            output_text_list = state.get(
                "raw_tts_text", state.get("raw_output_text", [])
            )
            tts_state = {"text_prompt": "".join(output_text_list)}
            total += TextToSpeechPage().get_raw_price(tts_state)

        if state.get("input_face"):
            total += 1

        return total

    def additional_notes(self):
        try:
            model = LargeLanguageModels[gui.session_state["selected_model"]].value
        except KeyError:
            model = "LLM"
        notes = f"\n*Breakdown: {math.ceil(self.get_total_linked_usage_cost_in_credits())} ({model}) + {self.PROFIT_CREDITS}/run*"

        if (
            gui.session_state.get("tts_provider")
            == TextToSpeechProviders.ELEVEN_LABS.name
        ):
            notes += f" *+ {TextToSpeechPage().get_cost_note()} (11labs)*"

        if gui.session_state.get("input_face"):
            notes += " *+ 1 (lipsync)*"

        return notes

    def run_v2(
        self,
        request: "VideoBotsPage.RequestModel",
        response: "VideoBotsPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        if request.tts_provider == TextToSpeechProviders.ELEVEN_LABS.name and not (
            self.is_current_user_paying() or self.is_current_user_admin()
        ):
            raise UserError(
                """
                Please purchase Gooey.AI credits to use ElevenLabs voices <a href="/account">here</a>.
                """
            )

        llm_model = LargeLanguageModels[request.selected_model]
        user_input = (request.input_prompt or "").strip()
        if not (
            user_input
            or request.input_audio
            or request.input_images
            or request.input_documents
        ):
            return

        asr_msg, user_input = yield from self.asr_step(
            model=llm_model, request=request, response=response, user_input=user_input
        )

        ocr_texts = yield from self.document_understanding_step(request=request)

        request.translation_model = (
            request.translation_model or DEFAULT_TRANSLATION_MODEL
        )
        user_input = yield from self.input_translation_step(
            request=request, user_input=user_input, ocr_texts=ocr_texts
        )

        yield from self.build_final_prompt(
            request=request, response=response, user_input=user_input, model=llm_model
        )

        yield from self.llm_loop(
            request=request,
            response=response,
            model=llm_model,
            asr_msg=asr_msg,
        )

        yield from self.tts_step(model=llm_model, request=request, response=response)

        yield from self.lipsync_step(request, response)

    def document_understanding_step(self, request):
        ocr_texts = []
        if request.document_model and request.input_images:
            yield "Running Azure Form Recognizer..."
            for url in request.input_images:
                ocr_text = (
                    azure_form_recognizer(url, model_id="prebuilt-read")
                    .get("content", "")
                    .strip()
                )
                if not ocr_text:
                    continue
                ocr_texts.append(ocr_text)
        if request.input_documents:
            import pandas as pd

            file_url_metas = yield from flatapply_parallel(
                lambda f_url: doc_or_yt_url_to_file_metas(f_url)[1],
                request.input_documents,
                message="Extracting Input Documents...",
            )
            for f_url, file_meta in file_url_metas:
                pages = doc_url_to_text_pages(
                    f_url=f_url,
                    file_meta=file_meta,
                    selected_asr_model=request.asr_model,
                )
                if isinstance(pages, pd.DataFrame):
                    ocr_texts.append(pages.to_csv(index=False))
                elif len(pages) <= 1:
                    ocr_texts.append("\n\n---\n\n".join(pages))
                else:
                    ocr_texts.append(json.dumps(pages))
        return ocr_texts

    def asr_step(self, model, request, response, user_input):
        if request.input_audio and not model.is_audio_model:
            if not request.asr_model:
                request.asr_model, request.asr_language = infer_asr_model_and_language(
                    request.user_language or ""
                )
            selected_model = AsrModels[request.asr_model]
            yield f"Transcribing using {selected_model.value}..."
            asr_output = run_asr(
                audio_url=request.input_audio,
                selected_model=request.asr_model,
                language=request.asr_language,
                speech_translation_target=(
                    "en" if request.asr_task == "translate" else None
                ),
                input_prompt=request.asr_prompt,
            )
            asr_msg = f'🎧: "{asr_output}"'
            response.output_text = [asr_msg] * request.num_outputs
            user_input = f"{asr_output}\n\n{user_input}".strip()
        else:
            asr_msg = None
        return asr_msg, user_input

    def input_translation_step(self, request, user_input, ocr_texts):
        # translate input text
        if (
            should_translate_lang(request.user_language)
            and not request.asr_task == "translate"
        ):
            yield "Translating Input to English..."
            user_input = run_translate(
                texts=[user_input],
                source_language=request.user_language,
                target_language="en",
                glossary_url=request.input_glossary_document,
                model=request.translation_model,
            )[0]
        if ocr_texts and request.user_language:
            yield "Translating Input Documents to English..."
            ocr_texts = run_translate(
                texts=ocr_texts,
                source_language="auto",
                target_language="en",
            )
        for text in ocr_texts:
            user_input = f"Exracted Text: {text!r}\n\n{user_input}"
        return user_input

    def build_final_prompt(self, request, response, user_input, model):
        # construct the system prompt
        bot_script = (request.bot_script or "").strip()
        if bot_script:
            bot_script = render_prompt_vars(bot_script, gui.session_state)
            # insert to top
            system_prompt = {"role": CHATML_ROLE_SYSTEM, "content": bot_script}
        else:
            system_prompt = None
        # save raw input for reference
        response.raw_input_text = user_input
        user_input = yield from self.search_step(request, response, user_input, model)
        # construct user prompt
        user_prompt = format_chat_entry(
            role=CHATML_ROLE_USER,
            content_text=user_input,
            input_images=request.input_images,
            input_audio=request.input_audio,
            input_documents=request.input_documents,
        )
        # truncate the history to fit the model's max tokens
        max_history_tokens = (
            model.context_window
            - calc_gpt_tokens(filter(None, [system_prompt, user_input]))
            - request.max_tokens
            - SAFETY_BUFFER
        )
        clip_idx = convo_window_clipper(
            request.messages,
            max_history_tokens,
        )
        history_prompt = request.messages[clip_idx:]
        response.final_prompt = list(
            filter(None, [system_prompt, *history_prompt, user_prompt])
        )
        # ensure input script is not too big
        max_allowed_tokens = model.context_window - calc_gpt_tokens(
            response.final_prompt
        )
        if max_allowed_tokens < 0:
            raise UserError("Input Script is too long! Please reduce the script size.")
        request.max_tokens = min(max_allowed_tokens, request.max_tokens)

    def search_step(self, request, response, user_input, model):
        # if documents are provided, run doc search on the saved msgs and get back the references
        if request.documents:
            # formulate the search query as a history of all the messages
            query_msgs = request.messages + [
                format_chat_entry(role=CHATML_ROLE_USER, content_text=user_input)
            ]
            clip_idx = convo_window_clipper(query_msgs, model.context_window // 2)
            query_msgs = query_msgs[clip_idx:]

            chat_history = messages_as_prompt(query_msgs)

            query_instructions = (request.query_instructions or "").strip()
            if query_instructions:
                yield "Creating search query..."
                response.final_search_query = generate_final_search_query(
                    request=request,
                    response=response,
                    instructions=query_instructions,
                    context={"messages": chat_history},
                ).strip()
            else:
                query_msgs.reverse()
                response.final_search_query = "\n---\n".join(
                    get_entry_text(entry) for entry in query_msgs
                )

            keyword_instructions = (request.keyword_instructions or "").strip()
            if keyword_instructions:
                yield "Finding keywords..."
                k_request = request.model_copy()
                # other models dont support JSON mode
                k_request.selected_model = LargeLanguageModels.gpt_4_o.name
                k_request.max_tokens = 4096
                keyword_query = json.loads(
                    generate_final_search_query(
                        request=k_request,
                        response=response,
                        instructions=keyword_instructions,
                        context={"messages": chat_history},
                        response_format_type="json_object",
                    ),
                )
                if keyword_query and isinstance(keyword_query, dict):
                    keyword_query = list(keyword_query.values())[0]
                response.final_keyword_query = keyword_query

            if response.final_search_query:  # perform doc search
                response.references = yield from get_top_k_references(
                    DocSearchRequest.model_validate(
                        {
                            **request.model_dump(),
                            **response.model_dump(),
                            "search_query": response.final_search_query,
                            "keyword_query": response.final_keyword_query,
                        },
                    ),
                    current_user=self.request.user,
                )
            if request.use_url_shortener:
                for reference in response.references:
                    reference["url"] = ShortenedURL.objects.get_or_create_for_workflow(
                        url=reference["url"],
                        user=self.request.user,
                        workflow=Workflow.VIDEO_BOTS,
                    )[0].shortened_url()
        # if doc search is successful, add the search results to the user prompt
        if response.references:
            # add task instructions
            task_instructions = render_prompt_vars(
                request.task_instructions, gui.session_state
            )
            user_input = (
                references_as_prompt(response.references)
                + f"\n**********\n{task_instructions.strip()}\n**********\n"
                + user_input
            )
        return user_input

    def llm_loop(
        self,
        *,
        request: "VideoBotsPage.RequestModel",
        response: "VideoBotsPage.ResponseModel",
        model: LargeLanguageModels,
        asr_msg: str | None = None,
        prev_output_text: list[str] | None = None,
    ) -> typing.Iterator[str | None]:
        yield f"Summarizing with {model.value}..."

        audio_session_extra = None
        if model.is_audio_model:
            audio_session_extra = {}
            if request.openai_voice_name:
                audio_session_extra["voice"] = request.openai_voice_name

        tools = self.get_current_llm_tools()
        chunks: typing.Generator[list[dict], None, None] = run_language_model(
            model=request.selected_model,
            messages=response.final_prompt,
            max_tokens=request.max_tokens,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
            response_format_type=request.response_format_type,
            tools=list(tools.values()),
            stream=True,
            audio_url=request.input_audio,
            audio_session_extra=audio_session_extra,
        )

        tool_calls = None
        output_text = None

        for i, choices in enumerate(chunks):
            if not choices:
                continue

            tool_calls = choices[0].get("tool_calls")
            output_text = [
                (prev_text + "\n\n" + entry["content"]).strip()
                for prev_text, entry in zip_longest(
                    (prev_output_text or []), choices, fillvalue=""
                )
            ]

            try:
                response.raw_input_text = choices[0]["input_audio_transcript"]
            except KeyError:
                pass
            try:
                response.output_audio += [choices[0]["audio_url"]]
            except KeyError:
                pass

            # save raw model response without citations and translation for history
            response.raw_output_text = [
                "".join(snippet for snippet, _ in parse_refs(text, response.references))
                for text in output_text
            ]

            output_text = yield from self.output_translation_step(
                request, response, output_text
            )

            if response.references:
                citation_style = (
                    request.citation_style and CitationStyles[request.citation_style]
                ) or None
                all_refs_list = apply_response_formattings_prefix(
                    output_text, response.references, citation_style
                )
            else:
                citation_style = None
                all_refs_list = None

            if asr_msg:
                output_text = [asr_msg + "\n\n" + text for text in output_text]

            response.output_text = output_text

            finish_reason = [entry.get("finish_reason") for entry in choices]
            if all(finish_reason):
                if all_refs_list:
                    apply_response_formattings_suffix(
                        all_refs_list, response.output_text, citation_style
                    )
                response.finish_reason = finish_reason
            else:
                yield f"Streaming{str(i + 1).translate(SUPERSCRIPT)} {model.value}..."

        if not tool_calls:
            return
        response.final_prompt.append(
            dict(
                role=choices[0]["role"],
                content=choices[0]["content"],
                tool_calls=tool_calls,
            )
        )
        for call in tool_calls:
            result = yield from exec_tool_call(call, tools)
            response.final_prompt.append(
                dict(
                    role="tool",
                    content=json.dumps(result),
                    tool_call_id=call["id"],
                ),
            )
        yield from self.llm_loop(
            request=request,
            response=response,
            model=model,
            prev_output_text=output_text,
        )

    def output_translation_step(self, request, response, output_text):
        from daras_ai_v2.bots import parse_bot_html

        # translate response text
        if should_translate_lang(request.user_language):
            yield f"Translating response to {request.user_language}..."
            output_text = run_translate(
                texts=output_text,
                source_language="en",
                target_language=request.user_language,
                glossary_url=request.output_glossary_document,
                model=request.translation_model,
            )
            # save translated response for tts
            response.raw_tts_text = [
                "".join(snippet for snippet, _ in parse_refs(text, response.references))
                for text in output_text
            ]

        # remove html tags from the output text for tts
        raw_tts_text = [
            parse_bot_html(text)[1] for text in response.raw_tts_text or output_text
        ]
        if raw_tts_text != output_text:
            response.raw_tts_text = raw_tts_text

        return output_text

    def tts_step(self, model, request, response):
        if request.tts_provider and not model.is_audio_model:
            response.output_audio = []
            for text in response.raw_tts_text or response.raw_output_text:
                tts_state = TextToSpeechPage.RequestModel.model_validate(
                    {**gui.session_state, "text_prompt": text}
                ).model_dump()
                yield from TextToSpeechPage(request=self.request).run(tts_state)
                response.output_audio.append(tts_state["audio_url"])

    def lipsync_step(self, request, response):
        if request.input_face and response.output_audio:
            response.output_video = []
            for audio_url in response.output_audio:
                lip_state = LipsyncPage.RequestModel.model_validate(
                    {
                        **gui.session_state,
                        "input_audio": audio_url,
                        "selected_model": request.lipsync_model,
                    }
                ).model_dump()
                yield from LipsyncPage(request=self.request).run(lip_state)
                response.output_video.append(lip_state["output_video"])

    def render_header_extra(self):
        if self.tab == RecipeTabs.run:
            render_demo_buttons_header(self.current_pr)

    def get_tabs(self):
        tabs = super().get_tabs()
        tabs.extend([RecipeTabs.integrations])
        return tabs

    def render_selected_tab(self):
        super().render_selected_tab()

        if self.tab == RecipeTabs.integrations:
            self.render_integrations_tab()

    def render_integrations_tab(self):
        from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

        gui.newline()

        # not signed in case
        if not self.request.user or self.request.user.is_anonymous:
            integrations_welcome_screen(title="Connect your Copilot")
            gui.newline()
            with gui.center():
                gui.anchor("Get Started", href=self.get_auth_url(), type="primary")
            return

        sr, pr = self.current_sr_pr

        # make user the user knows that they are on a saved run not the published run
        if pr and pr.saved_run_id != sr.id:
            last_saved_url = self.app_url(
                tab=RecipeTabs.integrations, example_id=pr.published_run_id
            )
            gui.caption(
                f"Note: You seem to have unpublished changes. Integrations use the [last saved version]({last_saved_url}), not the currently visible edits.",
                className="text-center text-muted",
            )

        # see which integrations are available to the user for the published run
        integrations_q = Q(published_run=pr) | Q(
            saved_run__example_id=pr.published_run_id
        )
        if not self.is_current_user_admin():
            integrations_q &= Q(workspace=self.current_workspace)

        integrations_qs: QuerySet[BotIntegration] = BotIntegration.objects.filter(
            integrations_q
        ).order_by("platform", "-created_at")

        run_title = get_title_breadcrumbs(VideoBotsPage, sr, pr).h1_title

        # no connected integrations on this run
        if not (integrations_qs and integrations_qs.exists()):
            self.render_integrations_add(
                label="#### Connect your Copilot",
                run_title=run_title,
                pr=pr,
            )
            return

        # this gets triggered on the /add route
        if gui.session_state.pop("--add-integration", None):
            self.render_integrations_add(
                label="#### Add a New Integration to your Copilot",
                run_title=run_title,
                pr=pr,
            )
            with gui.center():
                if gui.button("Return to Test & Configure"):
                    cancel_url = self.current_app_url(RecipeTabs.integrations)
                    raise gui.RedirectException(cancel_url)
            return

        with gui.center():
            # signed in, can edit, and has connected botintegrations on this run
            self.render_integrations_settings(
                integrations=list(integrations_qs), run_title=run_title
            )

    def render_integrations_add(self, label: str, run_title: str, pr: PublishedRun):
        from routers.facebook_api import fb_connect_url, wa_connect_url
        from routers.slack_api import slack_connect_url

        gui.write(label, unsafe_allow_html=True, className="text-center")

        can_edit = (
            self.request.user
            and WorkflowAccessLevel.can_user_edit_published_run(
                workspace=self.current_workspace,
                user=self.request.user,
                pr=pr,
            )
        )

        gui.newline()

        pressed_platform = None
        with (
            gui.tag("table", className="d-flex justify-content-center"),
            gui.tag("tbody"),
        ):
            for choice in connect_choices:
                with gui.tag("tr"):
                    with gui.tag("td"):
                        if gui.button(
                            f'<img src="{choice.img}" alt="{choice.platform.name}" style="max-width: 80%; max-height: 90%" draggable="false">',
                            className="p-0 border border-1 border-secondary rounded",
                            style=dict(width="160px", height="60px"),
                        ):
                            pressed_platform = choice.platform
                    with gui.tag("td", className="ps-3"):
                        gui.caption(choice.label)

        if not can_edit:
            gui.caption(
                "P.S. You're not an owner of this saved workflow, so we'll create a copy of it in your Saved Runs.",
                className="text-center text-muted",
            )

        if pressed_platform:
            if not can_edit:
                run_title = f"{self.request.user and self.request.user.first_name_possesive()} {run_title}"
                pr = pr.duplicate(
                    user=self.request.user,
                    workspace=self.current_workspace,
                    title=run_title,
                    notes=pr.notes,
                    public_access=WorkflowAccessLevel.VIEW_ONLY,
                )

            match pressed_platform:
                case Platform.WEB:
                    bi = BotIntegration.objects.create(
                        name=run_title,
                        created_by=self.request.user,
                        workspace=self.current_workspace,
                        platform=Platform.WEB,
                    )
                    redirect_url = connect_bot_to_published_run(bi, pr, overwrite=True)
                case Platform.WHATSAPP:
                    redirect_url = wa_connect_url(pr.id)
                case Platform.SLACK:
                    redirect_url = slack_connect_url(pr.id)
                case Platform.FACEBOOK:
                    redirect_url = fb_connect_url(pr.id)
                case _:
                    raise ValueError(f"Unsupported platform: {pressed_platform}")

            if not self.is_current_user_admin():
                send_integration_attempt_email.delay(
                    user_id=self.request.user.id,
                    platform=pressed_platform,
                    run_url=self.current_app_url() or "",
                )
            raise gui.RedirectException(redirect_url)

        gui.newline()
        api_tab_url = self.current_app_url(RecipeTabs.run_as_api)
        gui.write(
            f"Or use [our API]({api_tab_url}) to build custom integrations with your server.",
            className="text-center",
        )

    def render_integrations_settings(
        self, integrations: list[BotIntegration], run_title: str
    ):
        from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button

        gui.markdown("#### Configure your Copilot")
        gui.newline()

        if len(integrations) > 1:
            with gui.div(
                style={"width": "100%", "maxWidth": "500px", "textAlign": "left"}
            ):
                integrations_map = {i.id: i for i in integrations}
                bi_id = gui.selectbox(
                    label="",
                    options=integrations_map.keys(),
                    format_func=lambda bi_id: f"{Platform(integrations_map[bi_id].platform).get_icon()} &nbsp; {integrations_map[bi_id].name}",
                    key="bi_id",
                )
                bi = integrations_map[bi_id]
                old_bi_id = gui.session_state.get("old_bi_id", bi_id)
                if bi_id != old_bi_id:
                    raise gui.RedirectException(
                        self.current_app_url(
                            RecipeTabs.integrations,
                            path_params=dict(integration_id=bi.api_integration_id()),
                        )
                    )
                gui.session_state["old_bi_id"] = bi_id
        else:
            bi = integrations[0]

        if bi.platform == Platform.WEB:
            web_widget_config(
                bi=bi,
                user=self.request.user,
                hostname=self.request.url and self.request.url.hostname,
            )
            with gui.div(className="w-100"):
                gui.write("---")

        icon = Platform(bi.platform).get_icon()
        with gui.div(className="w-100 text-start"):
            test_link = bi.get_bot_test_link()
            col1, col2 = gui.columns(2, style={"alignItems": "center"})
            with col1:
                gui.write("###### Connected To")
                gui.write(f"{icon} {bi}", unsafe_allow_html=True)
            with col2:
                if not test_link:
                    gui.write("Message quicklink not available.")
                elif bi.platform == Platform.TWILIO:
                    copy_to_clipboard_button(
                        f"{icons.link} Copy Phone Number",
                        value=bi.twilio_phone_number.as_e164,
                        type="secondary",
                    )
                else:
                    copy_to_clipboard_button(
                        f"{icons.link} Copy {Platform(bi.platform).label} Link",
                        value=test_link,
                        type="secondary",
                    )

                if bi.platform == Platform.FACEBOOK:
                    gui.anchor(
                        '<i class="fa-regular fa-inbox"></i> Open Inbox',
                        "https://www.facebook.com/latest/inbox",
                        unsafe_allow_html=True,
                        new_tab=True,
                    )

            col1, col2 = gui.columns(2, style={"alignItems": "center"})
            with col1:
                gui.write("###### Test")
                gui.caption(f"Send a test message via {Platform(bi.platform).label}.")
            with col2:
                if not test_link:
                    gui.write("Message quicklink not available.")
                elif bi.platform == Platform.FACEBOOK:
                    gui.anchor(
                        f"{icon} Open Profile",
                        test_link,
                        unsafe_allow_html=True,
                        new_tab=True,
                    )
                elif bi.platform == Platform.TWILIO:
                    gui.anchor(
                        '<i class="fa-regular fa-phone"></i> Start Voice Call',
                        test_link,
                        unsafe_allow_html=True,
                        new_tab=True,
                    )
                    gui.anchor(
                        '<i class="fa-regular fa-sms"></i> Send SMS',
                        str(furl("sms:") / bi.twilio_phone_number.as_e164),
                        unsafe_allow_html=True,
                        new_tab=True,
                    )
                else:
                    gui.anchor(
                        f"{icon} Message {bi.get_display_name()}",
                        test_link,
                        unsafe_allow_html=True,
                        new_tab=True,
                    )

            col1, col2 = gui.columns(2, style={"alignItems": "center"})
            with col1:
                gui.write("###### Understand your Users")
                gui.caption("See real-time analytics.")
            with col2:
                gui.anchor(
                    "📊 View Analytics",
                    str(
                        furl(
                            self.current_app_url(
                                RecipeTabs.integrations,
                                path_params=dict(
                                    integration_id=bi.api_integration_id()
                                ),
                            )
                        )
                        / "stats/"
                    ),
                    new_tab=True,
                )
                if bi.platform == Platform.TWILIO and bi.twilio_phone_number_sid:
                    gui.anchor(
                        f"{icon} Open Twilio Console",
                        str(
                            furl(
                                "https://console.twilio.com/us1/develop/phone-numbers/manage/incoming/"
                            )
                            / bi.twilio_phone_number_sid
                            / "calls"
                        ),
                        unsafe_allow_html=True,
                        new_tab=True,
                    )

            if bi.platform == Platform.WHATSAPP and bi.wa_business_waba_id:
                col1, col2 = gui.columns(2, style={"alignItems": "center"})
                with col1:
                    gui.write("###### WhatsApp Business Management")
                    gui.caption(
                        "Access your WhatsApp account on Meta to approve message templates, etc."
                    )
                with col2:
                    gui.anchor(
                        "Business Settings",
                        str(
                            furl(
                                "https://business.facebook.com/settings/whatsapp-business-accounts/"
                            )
                            / bi.wa_business_waba_id
                        ),
                        new_tab=True,
                    )
                    gui.anchor(
                        "WhatsApp Manager",
                        str(
                            furl(
                                "https://business.facebook.com/wa/manage/home/",
                                query_params=dict(waba_id=bi.wa_business_waba_id),
                            )
                        ),
                        new_tab=True,
                    )

            col1, col2 = gui.columns(2, style={"alignItems": "center"})
            with col1:
                gui.write("###### Add Integration")
                gui.caption(f"Add another connection for {run_title}.")
            with col2:
                gui.anchor(
                    f'<img align="left" width="24" height="24" src="{icons.integrations_img}"> &nbsp; Add Integration',
                    str(furl(self.current_app_url(RecipeTabs.integrations)) / "add/"),
                    unsafe_allow_html=True,
                )

            gui.write("---")
            gui.newline()
            general_integration_settings(
                user=self.request.user,
                workspace=self.current_workspace,
                bi=bi,
                has_test_link=bool(test_link),
            )
            gui.write("---")

            if bi.platform in [Platform.SLACK, Platform.WHATSAPP, Platform.TWILIO]:
                gui.newline()
                broadcast_input(bi)
                gui.write("---")

            col1, col2 = gui.columns(2, style={"alignItems": "center"})
            with col1:
                gui.write("###### Disconnect")
                gui.caption(
                    f"Disconnect {run_title} from {Platform(bi.platform).label} {bi.get_display_name()}."
                )
            with col2:
                if gui.button(
                    "💔️ Disconnect",
                    key="btn_disconnect",
                ):
                    bi.saved_run = None
                    bi.published_run = None
                    bi.save()
                    gui.rerun()


def messages_as_prompt(query_msgs: list[dict]) -> str:
    return "\n".join(
        f'{entry["role"]}: """{get_entry_text(entry)}"""' for entry in query_msgs
    )


def infer_asr_model_and_language(
    user_language: str, default=AsrModels.whisper_large_v2
) -> tuple[str, str]:
    asr_lang = None
    user_lang = user_language.lower()
    if "am" in user_lang:
        asr_model = AsrModels.usm
        asr_lang = "am-et"
    elif "hi" in user_lang:
        asr_model = AsrModels.nemo_hindi
    elif "te" in user_lang:
        asr_model = AsrModels.whisper_telugu_large_v2
    elif "bho" in user_lang:
        asr_model = AsrModels.vakyansh_bhojpuri
    elif "sw" in user_lang:
        asr_model = AsrModels.seamless_m4t_v2
        asr_lang = "swh"
    else:
        asr_model = default
    return asr_model.name, asr_lang


def convo_window_clipper(
    window: list[ConversationEntry],
    max_tokens,
    *,
    step=2,
):
    for i in range(len(window) - 2, -1, -step):
        if calc_gpt_tokens(window[i:]) > max_tokens:
            return i + step
    return 0


def exec_tool_call(call: dict, tools: dict[str, "LLMTool"]):
    tool_name = call["function"]["name"]
    tool_args = call["function"]["arguments"]
    tool = tools[tool_name]
    yield f"🛠 {tool.label}..."
    try:
        kwargs = json.loads(tool_args)
    except json.JSONDecodeError as e:
        return dict(error=repr(e))
    return tool(**kwargs)


class ConnectChoice(typing.NamedTuple):
    platform: Platform
    img: str
    label: str


connect_choices = [
    ConnectChoice(
        platform=Platform.WEB,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2bd17e74-1dcf-11ef-8207-02420a000136/thumbs/image_400x400.png",
        label="Connect to your own App or Website.",
    ),
    ConnectChoice(
        platform=Platform.WHATSAPP,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1e49ad50-d6c9-11ee-99c3-02420a000123/thumbs/Digital_Inline_Green_400x400.png",
        label="[Read our guide](https://docs.gooey.ai/guides/how-to-deploy-an-ai-copilot/deploy-on-whatsapp) to connect your own mobile # (that's not already on WhatsApp) or [upgrade](https://gooey.ai/account/billing/) for a number on us.",
    ),
    ConnectChoice(
        platform=Platform.SLACK,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ee8c5b1c-d6c8-11ee-b278-02420a000126/thumbs/image_400x400.png",
        label="Connect to a Slack Channel. [Help Guide](https://gooey.ai/docs/guides/copilot/deploy-to-slack)",
    ),
    ConnectChoice(
        platform=Platform.FACEBOOK,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/9f201a92-1e9d-11ef-884b-02420a000134/thumbs/image_400x400.png",
        label="Connect to a Facebook Page you own. [Help Guide](https://gooey.ai/docs/guides/copilot/deploy-to-facebook)",
    ),
]
