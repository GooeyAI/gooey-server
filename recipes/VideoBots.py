import json
import math
import mimetypes
import typing

import gooey_gui as gui
from django.db.models import QuerySet, Q
from furl import furl
from pydantic import BaseModel, Field

from bots.models import (
    BotIntegration,
    Platform,
    PublishedRun,
    PublishedRunVisibility,
)
from bots.models import Workflow
from celeryapp.tasks import send_integration_attempt_email
from daras_ai.image_input import (
    truncate_text_words,
)
from daras_ai_v2 import icons, settings
from daras_ai_v2.asr import (
    translation_model_selector,
    translation_language_selector,
    run_translate,
    TranslationModels,
    AsrModels,
    asr_language_selector,
    run_asr,
    should_translate_lang,
)
from daras_ai_v2.azure_doc_extract import (
    azure_form_recognizer,
    azure_form_recognizer_models,
)
from daras_ai_v2.base import BasePage, RecipeTabs
from daras_ai_v2.bot_integration_connect import connect_bot_to_published_run
from daras_ai_v2.bot_integration_widgets import (
    general_integration_settings,
    slack_specific_settings,
    twilio_specific_settings,
    broadcast_input,
    get_bot_test_link,
    web_widget_config,
    get_web_widget_embed_code,
    integrations_welcome_screen,
)
from daras_ai_v2.doc_search_settings_widgets import (
    query_instructions_widget,
    keyword_instructions_widget,
    doc_search_advanced_settings,
    doc_extract_selector,
    bulk_documents_uploader,
    citation_style_selector,
    SUPPORTED_SPREADSHEET_TYPES,
)
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.field_render import field_title_desc, field_desc, field_title
from daras_ai_v2.glossary import validate_glossary_document
from daras_ai_v2.language_model import (
    run_language_model,
    calc_gpt_tokens,
    ConversationEntry,
    LargeLanguageModels,
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    CHATML_ROLE_SYSTEM,
    get_entry_images,
    get_entry_text,
    format_chat_entry,
    SUPERSCRIPT,
)
from daras_ai_v2.language_model_settings_widgets import (
    language_model_settings,
    language_model_selector,
    LanguageModelSettings,
)
from daras_ai_v2.lipsync_api import LipsyncSettings, LipsyncModel
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.prompt_vars import render_prompt_vars
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.query_params_util import extract_query_params
from daras_ai_v2.search_ref import (
    parse_refs,
    CitationStyles,
    apply_response_formattings_prefix,
    apply_response_formattings_suffix,
)
from daras_ai_v2.text_output_widget import text_output
from daras_ai_v2.text_to_speech_settings_widgets import (
    TextToSpeechProviders,
    text_to_speech_settings,
    text_to_speech_provider_selector,
    elevenlabs_init_state,
)
from daras_ai_v2.vector_search import DocSearchRequest
from functions.recipe_functions import LLMTools
from recipes.DocSearch import (
    get_top_k_references,
    references_as_prompt,
)
from recipes.GoogleGPT import SearchReference
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage, TextToSpeechSettings
from url_shortener.models import ShortenedURL

DEFAULT_COPILOT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7a3127ec-1f71-11ef-aa2b-02420a00015d/Copilot.jpg"
GRAYCOLOR = "#00000073"

SAFETY_BUFFER = 100


def exec_tool_call(call: dict):
    tool_name = call["function"]["name"]
    tool = LLMTools[tool_name]
    yield f"🛠 {tool.label}..."
    kwargs = json.loads(call["function"]["arguments"])
    return tool.fn(**kwargs)


class ReplyButton(typing.TypedDict):
    id: str
    title: str


class VideoBotsPage(BasePage):
    PROFIT_CREDITS = 3

    title = "Copilot for your Enterprise"  # "Create Interactive Video Bots"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/8c014530-88d4-11ee-aac9-02420a00016b/Copilot.png.png"
    workflow = Workflow.VIDEO_BOTS
    slug_versions = ["video-bots", "bots", "copilot"]

    sdk_group_name = "copilot"
    sdk_method_name = "completion"

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
        "translation_model": TranslationModels.google.name,
    }

    class RequestModelBase(BasePage.RequestModel):
        input_prompt: str | None
        input_audio: str | None
        input_images: list[FieldHttpUrl] | None
        input_documents: list[FieldHttpUrl] | None

        doc_extract_url: str | None = Field(
            title="📚 Document Extract Workflow",
            description="Select a workflow to extract text from documents and images.",
        )

        # conversation history/context
        messages: list[ConversationEntry] | None

        bot_script: str | None

        # llm model
        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )
        document_model: str | None = Field(
            title="🩻 Photo / Document Intelligence",
            description="When your copilot users upload a photo or pdf, what kind of document are they mostly likely to upload? "
            "(via [Azure](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/use-sdk-rest-api?view=doc-intel-3.1.0&tabs=linux&pivots=programming-language-rest-api))",
        )

        # doc search
        task_instructions: str | None
        query_instructions: str | None
        keyword_instructions: str | None
        documents: list[FieldHttpUrl] | None
        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

        embedding_model: typing.Literal[tuple(e.name for e in EmbeddingModels)] | None
        dense_weight: float | None = DocSearchRequest.__fields__[
            "dense_weight"
        ].field_info

        citation_style: typing.Literal[tuple(e.name for e in CitationStyles)] | None
        use_url_shortener: bool | None

        asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None = Field(
            title="Speech-to-Text Provider",
            description="Choose a model to transcribe incoming audio messages to text.",
        )
        asr_language: str | None = Field(
            title="Spoken Language",
            description="Choose a language to transcribe incoming audio messages to text.",
        )

        translation_model: (
            typing.Literal[tuple(e.name for e in TranslationModels)] | None
        )
        user_language: str | None = Field(
            title="User Language",
            description="Choose a language to translate incoming text & audio messages to English and responses back to your selected language. Useful for low-resource languages.",
        )
        # llm_language: str | None = "en" <-- implicit since this is hardcoded everywhere in the code base (from facebook and bots to slack and copilot etc.)
        input_glossary_document: FieldHttpUrl | None = Field(
            title="Input Glossary",
            description="""
Translation Glossary for User Langauge -> LLM Language (English)
            """,
        )
        output_glossary_document: FieldHttpUrl | None = Field(
            title="Output Glossary",
            description="""
Translation Glossary for LLM Language (English) -> User Langauge
            """,
        )

        lipsync_model: typing.Literal[tuple(e.name for e in LipsyncModel)] = (
            LipsyncModel.Wav2Lip.name
        )

        tools: list[LLMTools] | None = Field(
            title="🛠️ Tools",
            description="Give your copilot superpowers by giving it access to tools. Powered by [Function calling](https://platform.openai.com/docs/guides/function-calling).",
        )

    class RequestModel(
        LipsyncSettings, TextToSpeechSettings, LanguageModelSettings, RequestModelBase
    ):
        pass

    class ResponseModel(BaseModel):
        final_prompt: str | list[ConversationEntry] = []

        output_text: list[str] = []
        output_audio: list[FieldHttpUrl] = []
        output_video: list[FieldHttpUrl] = []

        # intermediate text
        raw_input_text: str | None
        raw_tts_text: list[str] | None
        raw_output_text: list[str] | None

        # doc search
        references: list[SearchReference] | None = []
        final_search_query: str | None
        final_keyword_query: str | list[str] | None

        # function calls
        output_documents: list[FieldHttpUrl] | None
        reply_buttons: list[ReplyButton] | None

        finish_reason: list[str] | None

    @classmethod
    def get_openapi_extra(cls) -> dict[str, typing.Any]:
        return {
            "x-sdk-group-name": cls.sdk_group_name,
            "x-sdk-method-name": cls.sdk_method_name,
        }

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_COPILOT_META_IMG

    def related_workflows(self):
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.DeforumSD import DeforumSDPage
        from recipes.DocSearch import DocSearchPage

        return [
            LipsyncTTSPage,
            DocSearchPage,
            DeforumSDPage,
            CompareText2ImgPage,
        ]

    def preview_description(self, state: dict) -> str:
        return "Create customized chatbots from your own docs/PDF/webpages. Craft your own bot prompts using the creative GPT3, fast GPT 3.5-turbo or powerful GPT4 & optionally prevent hallucinations by constraining all answers to just your citations. Available as Facebook, Instagram, WhatsApp bots or via API. Add multi-lingual speech recognition and text-to-speech in 100+ languages and even video responses. Collect 👍🏾 👎🏽 feedback + see usage & retention graphs too! This is the workflow that powers https://Farmer.CHAT and it's yours to tweak."
        # return "Create an amazing, interactive AI videobot with just a GPT3 script + a video clip or photo. To host it on your own site or app, contact us at support@gooey.ai"

    def get_submit_container_props(self):
        return {}

    def render_description(self):
        gui.write(
            """
Have you ever wanted to create a bot that you could talk to about anything? Ever wanted to create your own https://dara.network/RadBots or https://Farmer.CHAT? This is how.

This workflow takes a dialog LLM prompt describing your character, a collection of docs & links and optional an video clip of your bot’s face and  voice settings.

We use all these to build a bot that anyone can speak to about anything and you can host directly in your own site or app, or simply connect to your Facebook, WhatsApp or Instagram page.

How It Works:
1. Appends the user's question to the bottom of your dialog script.
2. Sends the appended script to OpenAI’s GPT3 asking it to respond to the question in the style of your character
3. Synthesizes your character's response as audio using your voice settings (using Google Text-To-Speech or Uberduck)
4. Lip syncs the face video clip to the voice clip
5. Shows the resulting video to the user

PS. This is the workflow that we used to create RadBots - a collection of Turing-test videobots, authored by leading international writers, singers and playwrights - and really inspired us to create Gooey.AI so that every person and organization could create their own fantastic characters, in any personality of their choosing. It's also the workflow that powers https://Farmer.CHAT and was demo'd at the UN General Assembly in April 2023 as a multi-lingual WhatsApp bot for Indian, Ethiopian and Kenyan farmers.
        """
        )

    def render_form_v2(self):
        gui.text_area(
            """
            #### 📝 Instructions
            """,
            key="bot_script",
            height=300,
        )

        language_model_selector(label="#### 🧠 Language Model")

        bulk_documents_uploader(
            """
            #### 📄 Knowledge
            Add documents or links to give your copilot a knowledge base. When asked a question, we'll search them to generate an answer with citations. 
            """,
            accept=["audio/*", "application/*", "video/*", "text/*"],
        )

        gui.markdown("#### 💪 Capabilities")
        if gui.checkbox(
            "##### 🗣️ Text to Speech & Lipsync",
            value=bool(gui.session_state.get("tts_provider")),
        ):
            text_to_speech_provider_selector(self)
            gui.write("---")

            enable_video = gui.checkbox(
                "##### 🫦 Add Lipsync Video",
                value=bool(gui.session_state.get("input_face")),
            )
        else:
            gui.session_state["tts_provider"] = None
            enable_video = False
        if enable_video:
            gui.file_uploader(
                """
                ###### 👩‍🦰 Input Face
                Upload a video or image (with a human face) to lipsync responses. mp4, mov, png, jpg or gif preferred.
                """,
                key="input_face",
            )
            enum_selector(
                LipsyncModel,
                label="###### Lipsync Model",
                key="lipsync_model",
                use_selectbox=True,
            )
            gui.write("---")
        else:
            gui.session_state["input_face"] = None
            gui.session_state.pop("lipsync_model", None)

        if gui.checkbox(
            "##### 🔠 Translation & Speech Recognition",
            value=bool(
                gui.session_state.get("user_language")
                or gui.session_state.get("asr_model")
            ),
        ):
            gui.caption(field_desc(self.RequestModel, "user_language"))
            col1, col2 = gui.columns(2)
            with col1:
                translation_model = translation_model_selector(allow_none=False)
            with col2:
                translation_language_selector(
                    model=translation_model,
                    label=f"###### {field_title(self.RequestModel, 'user_language')}",
                    key="user_language",
                )
            gui.write("---")

            col1, col2 = gui.columns(2, responsive=False)
            with col1:
                selected_model = enum_selector(
                    AsrModels,
                    label=f"###### {field_title(self.RequestModel, 'asr_model')}",
                    key="asr_model",
                    use_selectbox=True,
                    allow_none=True,
                    format_func=lambda x: AsrModels[x].value if x else "Auto Select",
                )
            if selected_model:
                with col2:
                    asr_language_selector(
                        AsrModels[selected_model],
                        label=f"###### {field_title(self.RequestModel, 'asr_language')}",
                        key="asr_language",
                    )
            else:
                gui.caption(
                    f"We'll automatically select an [ASR](https://gooey.ai/asr) model for you based on the {field_title(self.RequestModel, 'user_language')}."
                )
            gui.write("---")
        else:
            gui.session_state["translation_model"] = None
            gui.session_state["asr_model"] = None
            gui.session_state["user_language"] = None

        if gui.checkbox(
            "##### 🩻 Photo & Document Intelligence",
            value=bool(gui.session_state.get("document_model")),
        ):
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
            gui.write("---")
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
            "translation_model", TranslationModels.google.name
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
            gui.checkbox("🔗 Shorten Citation URLs", key="use_url_shortener")

            doc_extract_selector(self.request and self.request.user)

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

        gui.write("---")

        enum_multiselect(
            enum_cls=LLMTools,
            label="##### " + field_title_desc(self.RequestModel, "tools"),
            key="tools",
        )

    def fields_not_to_save(self):
        return ["elevenlabs_api_key"]

    def fields_to_save(self) -> [str]:
        fields = super().fields_to_save()
        try:
            fields.remove("elevenlabs_api_key")
        except ValueError:
            pass
        return fields

    def run_as_api_tab(self):
        elevenlabs_init_state(self)
        super().run_as_api_tab()

    def render_example(self, state: dict):
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

    def render_output(self):
        # chat window
        with gui.div(className="pb-3"):
            chat_list_view()
            pressed_send, new_inputs = chat_input_view()

        if pressed_send:
            self.on_send(*new_inputs)

        # clear chat inputs
        if gui.button("🗑️ Clear"):
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

        # render sources
        references = gui.session_state.get("references", [])
        if not references:
            return
        key = "sources-expander"
        with gui.expander("💁‍♀️ Sources", key=key):
            if not gui.session_state.get(key):
                return
            for idx, ref in enumerate(references):
                gui.write(f"**{idx + 1}**. [{ref['title']}]({ref['url']})")
                text_output(
                    "Source Document",
                    value=ref["snippet"],
                    label_visibility="collapsed",
                )

    def on_send(
        self,
        new_input_text: str,
        new_input_images: list[str],
        new_input_audio: str,
        new_input_documents: list[str],
    ):
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
                    content=prev_input,
                    images=prev_input_images,
                ),
                format_chat_entry(
                    role=CHATML_ROLE_ASSISTANT,
                    content=prev_output,
                ),
            ]

        # add new input to the state
        if new_input_documents:
            filenames = ", ".join(
                furl(url.strip("/")).path.segments[-1] for url in new_input_documents
            )
            new_input_text = f"Files: {filenames}\n\n{new_input_text}"
        gui.session_state["input_prompt"] = new_input_text
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
            gui.json(references)

        final_prompt = gui.session_state.get("final_prompt")
        if final_prompt:
            if isinstance(final_prompt, str):
                text_output("###### `final_prompt`", value=final_prompt, height=300)
            else:
                gui.write("###### `final_prompt`")
                gui.json(final_prompt)

        for k in ["raw_output_text", "output_text", "raw_tts_text"]:
            for idx, text in enumerate(gui.session_state.get(k) or []):
                gui.text_area(
                    f"###### `{k}[{idx}]`",
                    value=text,
                    disabled=True,
                )

        for idx, audio_url in enumerate(gui.session_state.get("output_audio", [])):
            gui.write(f"###### `output_audio[{idx}]`")
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

        model = LargeLanguageModels[request.selected_model]
        user_input = request.input_prompt.strip()
        if not (
            user_input
            or request.input_audio
            or request.input_images
            or request.input_documents
        ):
            return

        ocr_texts = []
        if request.document_model and (request.input_images or request.input_documents):
            yield "Running Azure Form Recognizer..."
            for url in (request.input_images or []) + (request.input_documents or []):
                ocr_text = (
                    azure_form_recognizer(url, model_id="prebuilt-read")
                    .get("content", "")
                    .strip()
                )
                if not ocr_text:
                    continue
                ocr_texts.append(ocr_text)

        if request.input_audio:
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
            )
            asr_msg = f"🎧 I heard: “{asr_output}”"
            response.output_text = [asr_msg] * request.num_outputs
            user_input = f"{asr_output}\n\n{user_input}".strip()
        else:
            asr_msg = None

        # translate input text
        translation_model = request.translation_model or TranslationModels.google.name
        if should_translate_lang(request.user_language):
            yield f"Translating Input to English..."
            user_input = run_translate(
                texts=[user_input],
                source_language=request.user_language,
                target_language="en",
                glossary_url=request.input_glossary_document,
                model=translation_model,
            )[0]

        if ocr_texts:
            yield f"Translating Image Text to English..."
            ocr_texts = run_translate(
                texts=ocr_texts,
                source_language="auto",
                target_language="en",
            )
            for text in ocr_texts:
                user_input = f"Exracted Text: {text!r}\n\n{user_input}"

        # consturct the system prompt
        bot_script = (request.bot_script or "").strip()
        if bot_script:
            bot_script = render_prompt_vars(bot_script, gui.session_state)
            # insert to top
            system_prompt = {"role": CHATML_ROLE_SYSTEM, "content": bot_script}
        else:
            system_prompt = None

        # save raw input for reference
        response.raw_input_text = user_input

        # if documents are provided, run doc search on the saved msgs and get back the references
        if request.documents:
            # formulate the search query as a history of all the messages
            query_msgs = request.messages + [
                format_chat_entry(role=CHATML_ROLE_USER, content=user_input)
            ]
            clip_idx = convo_window_clipper(query_msgs, model.context_window // 2)
            query_msgs = query_msgs[clip_idx:]

            chat_history = messages_as_prompt(query_msgs)

            query_instructions = (request.query_instructions or "").strip()
            if query_instructions:
                yield "Creating search query..."
                response.final_search_query = generate_final_search_query(
                    request=request,
                    instructions=query_instructions,
                    context={**gui.session_state, "messages": chat_history},
                )
            else:
                query_msgs.reverse()
                response.final_search_query = "\n---\n".join(
                    get_entry_text(entry) for entry in query_msgs
                )

            keyword_instructions = (request.keyword_instructions or "").strip()
            if keyword_instructions:
                yield "Finding keywords..."
                k_request = request.copy()
                # other models dont support JSON mode
                k_request.selected_model = LargeLanguageModels.gpt_4_turbo.name
                keyword_query = json.loads(
                    generate_final_search_query(
                        request=k_request,
                        instructions=keyword_instructions,
                        context={**gui.session_state, "messages": chat_history},
                        response_format_type="json_object",
                    ),
                )
                if keyword_query and isinstance(keyword_query, dict):
                    keyword_query = list(keyword_query.values())[0]
                response.final_keyword_query = keyword_query
            # return

            # perform doc search
            response.references = yield from get_top_k_references(
                DocSearchRequest.parse_obj(
                    {
                        **gui.session_state,
                        "search_query": response.final_search_query,
                        "keyword_query": response.final_keyword_query,
                    },
                ),
                current_user=self.request and self.request.user,
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

        # construct user prompt
        user_prompt = format_chat_entry(
            role=CHATML_ROLE_USER, content=user_input, images=request.input_images
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
        max_allowed_tokens = min(max_allowed_tokens, request.max_tokens)
        if max_allowed_tokens < 0:
            raise UserError("Input Script is too long! Please reduce the script size.")

        yield f"Summarizing with {model.value}..."
        chunks = run_language_model(
            model=request.selected_model,
            messages=[
                {"role": entry["role"], "content": entry["content"]}
                for entry in response.final_prompt
            ],
            max_tokens=max_allowed_tokens,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
            response_format_type=request.response_format_type,
            tools=request.tools,
            stream=True,
        )
        citation_style = (
            request.citation_style and CitationStyles[request.citation_style]
        ) or None
        for i, entries in enumerate(chunks):
            if not entries:
                continue
            output_text = [entry["content"] for entry in entries]
            if request.tools:
                # output_text, tool_call_choices = output_text
                response.output_documents = output_documents = []
                for call in entries[0].get("tool_calls") or []:
                    result = yield from exec_tool_call(call)
                    output_documents.append(result)

            # save model response without citations
            response.raw_output_text = [
                "".join(snippet for snippet, _ in parse_refs(text, response.references))
                for text in output_text
            ]

            # translate response text
            if should_translate_lang(request.user_language):
                yield f"Translating response to {request.user_language}..."
                output_text = run_translate(
                    texts=output_text,
                    source_language="en",
                    target_language=request.user_language,
                    glossary_url=request.output_glossary_document,
                    model=translation_model,
                )
                # save translated response for tts
                response.raw_tts_text = [
                    "".join(
                        snippet for snippet, _ in parse_refs(text, response.references)
                    )
                    for text in output_text
                ]

            if response.references:
                all_refs_list = apply_response_formattings_prefix(
                    output_text, response.references, citation_style
                )
            else:
                all_refs_list = None

            if asr_msg:
                output_text = [asr_msg + "\n\n" + text for text in output_text]
            response.output_text = output_text
            finish_reasons = [entry.get("finish_reason") for entry in entries]
            if all(finish_reasons):
                if all_refs_list:
                    apply_response_formattings_suffix(
                        all_refs_list, response.output_text, citation_style
                    )
                response.finish_reason = finish_reasons
            else:
                yield f"Streaming{str(i + 1).translate(SUPERSCRIPT)} {model.value}..."

        if not request.tts_provider:
            return
        response.output_audio = []
        for text in response.raw_tts_text or response.raw_output_text:
            tts_state = TextToSpeechPage.RequestModel.parse_obj(
                {**gui.session_state, "text_prompt": text}
            ).dict()
            yield from TextToSpeechPage(
                request=self.request, run_user=self.run_user
            ).run(tts_state)
            response.output_audio.append(tts_state["audio_url"])

        if not request.input_face:
            return
        response.output_video = []
        for audio_url in response.output_audio:
            lip_state = LipsyncPage.RequestModel.parse_obj(
                {
                    **gui.session_state,
                    "input_audio": audio_url,
                    "selected_model": request.lipsync_model,
                }
            ).dict()
            yield from LipsyncPage(request=self.request, run_user=self.run_user).run(
                lip_state
            )
            response.output_video.append(lip_state["output_video"])

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

        sr, pr = self.get_runs_from_query_params(
            *extract_query_params(gui.get_query_params())
        )

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
            integrations_q &= Q(billing_account_uid=self.request.user.uid)

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

        can_edit = self.is_current_user_admin() or self.can_user_edit_published_run(pr)

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
                run_title = f"{self.request.user.first_name_possesive()} {run_title}"
                pr = pr.duplicate(
                    user=self.request.user,
                    title=run_title,
                    notes=pr.notes,
                    visibility=PublishedRunVisibility.UNLISTED,
                )

            match pressed_platform:
                case Platform.WEB:
                    bi = BotIntegration.objects.create(
                        name=run_title,
                        billing_account_uid=self.request.user.uid,
                        platform=Platform.WEB,
                    )
                    redirect_url = connect_bot_to_published_run(bi, pr)
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

        if len(integrations) > 1:
            with gui.div(style={"minWidth": "500px", "textAlign": "left"}):
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
        icon = Platform(bi.platform).get_icon()

        if bi.platform == Platform.WEB:
            web_widget_config(bi, self.request.user)
            gui.newline()

        gui.newline()
        with gui.div(style={"width": "100%", "textAlign": "left"}):
            test_link = get_bot_test_link(bi)
            col1, col2 = gui.columns(2, style={"alignItems": "center"})
            with col1:
                gui.write("###### Connected To")
                gui.write(f"{icon} {bi}", unsafe_allow_html=True)
            with col2:
                if not test_link:
                    gui.write("Message quicklink not available.")
                elif bi.platform == Platform.TWILIO:
                    copy_to_clipboard_button(
                        '<i class="fa-regular fa-link"></i> Copy Phone Number',
                        value=bi.twilio_phone_number.as_e164,
                        type="secondary",
                    )
                else:
                    copy_to_clipboard_button(
                        f'<i class="fa-regular fa-link"></i> Copy {Platform(bi.platform).label} Link',
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
                elif bi.platform == Platform.WEB:
                    embed_code = get_web_widget_embed_code(bi)
                    copy_to_clipboard_button(
                        f"{icons.code} Copy Embed Code",
                        value=embed_code,
                        type="secondary",
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
                gui.caption(f"See real-time analytics.")
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
                        f"Access your WhatsApp account on Meta to approve message templates, etc."
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

            with gui.expander("Configure Settings 🛠️"):
                if bi.platform == Platform.SLACK:
                    slack_specific_settings(bi, run_title)
                if bi.platform == Platform.TWILIO:
                    twilio_specific_settings(bi)
                general_integration_settings(bi, self.request.user)

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


def chat_list_view():
    # render a reversed list view
    with gui.div(
        className="pb-1",
        style=dict(
            maxHeight="80vh",
            overflowY="scroll",
            display="flex",
            flexDirection="column-reverse",
            border="1px solid #c9c9c9",
        ),
    ):
        with gui.div(className="px-3"):
            show_raw_msgs = gui.checkbox("_Show Raw Output_")
        # render the last output
        with msg_container_widget(CHATML_ROLE_ASSISTANT):
            if show_raw_msgs:
                output_text = gui.session_state.get("raw_output_text", [])
            else:
                output_text = gui.session_state.get("output_text", [])
            output_video = gui.session_state.get("output_video", [])
            output_audio = gui.session_state.get("output_audio", [])
            if output_text:
                gui.write(f"**Assistant**")
                for idx, text in enumerate(output_text):
                    gui.write(text)
                    try:
                        gui.video(output_video[idx])
                    except IndexError:
                        try:
                            gui.audio(output_audio[idx])
                        except IndexError:
                            pass
            output_documents = gui.session_state.get("output_documents", [])
            if output_documents:
                for doc in output_documents:
                    gui.write(doc)
        messages = gui.session_state.get("messages", []).copy()
        # add last input to history if present
        if show_raw_msgs:
            input_prompt = gui.session_state.get("raw_input_text")
        else:
            input_prompt = gui.session_state.get("input_prompt")
        input_images = gui.session_state.get("input_images")
        input_audio = gui.session_state.get("input_audio")
        if input_prompt or input_images or input_audio:
            messages += [
                format_chat_entry(
                    role=CHATML_ROLE_USER, content=input_prompt, images=input_images
                ),
            ]
        # render history
        for entry in reversed(messages):
            with msg_container_widget(entry["role"]):
                images = get_entry_images(entry)
                text = get_entry_text(entry)
                if text or images or input_audio:
                    gui.write(f"**{entry['role'].capitalize()}**  \n{text}")
                if images:
                    for im in images:
                        gui.image(im, style={"maxHeight": "200px"})
                if input_audio:
                    gui.audio(input_audio)
                    input_audio = None


def chat_input_view() -> tuple[bool, tuple[str, list[str], str, list[str]]]:
    with gui.div(
        className="px-3 pt-3 d-flex gap-1",
        style=dict(background="rgba(239, 239, 239, 0.6)"),
    ):
        show_uploader_key = "--show-file-uploader"
        show_uploader = gui.session_state.setdefault(show_uploader_key, False)
        if gui.button(
            "📎",
            style=dict(height="3.2rem", backgroundColor="white"),
        ):
            show_uploader = not show_uploader
            gui.session_state[show_uploader_key] = show_uploader

        with gui.div(className="flex-grow-1"):
            new_input_text = gui.text_area("", placeholder="Send a message", height=50)

        pressed_send = gui.button("✈ Send", style=dict(height="3.2rem"))

    if show_uploader:
        uploaded_files = gui.file_uploader("", accept_multiple_files=True)
        new_input_images = []
        new_input_audio = None
        new_input_documents = []
        for f in uploaded_files:
            mime_type = mimetypes.guess_type(f)[0] or ""
            if mime_type.startswith("image/"):
                new_input_images.append(f)
            if mime_type.startswith("audio/") or mime_type.startswith("video/"):
                new_input_audio = f
            else:
                new_input_documents.append(f)
    else:
        new_input_images = None
        new_input_audio = None
        new_input_documents = None

    return (
        pressed_send,
        (
            new_input_text,
            new_input_images,
            new_input_audio,
            new_input_documents,
        ),
    )


def msg_container_widget(role: str):
    return gui.div(
        className="px-3 py-1 pt-2",
        style=dict(
            background=(
                "rgba(239, 239, 239, 0.6)" if role == CHATML_ROLE_USER else "#fff"
            ),
        ),
    )


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
        label="Bring your own WhatsApp number to connect. Need a new one? Email [sales@gooey.ai](mailto:sales@gooey.ai) for help.",
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
