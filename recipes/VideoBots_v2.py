import html
import json
import math
import traceback
import typing
from enum import Enum
from functools import cached_property
from itertools import zip_longest

import sentry_sdk
import typing_extensions
from pydantic import BaseModel, Field

import gooey_gui as gui
from ai_models.llm_openapi import LLMMarker
from ai_models.models import AIModelSpec
from app_users.models import AppUser
from bots.models import (
    BotIntegration,
    Platform,
    PublishedRun,
    SavedRun,
    Workflow,
)
from bots.models.message_thread import MessageThread
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import exceptions, icons, settings
from daras_ai_v2.asr import (
    AsrModels,
    TranslationModels,
    asr_language_selector,
    asr_model_selector,
    run_asr,
    run_translate,
    should_translate_lang,
    translation_language_selector,
    translation_model_selector,
)
from daras_ai_v2.azure_doc_extract import (
    azure_form_recognizer,
)
from daras_ai_v2.base_v2 import (
    FILL_HEIGHT_EDITOR_CSS,
    STARTING_STATE,
    VARIABLES_DIALOG_CSS,
    BasePage,
    RecipeTabs,
)
from daras_ai_v2.bot_integration_widgets import integrations_welcome_screen
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
from daras_ai_v2.fastapi_tricks import get_api_route_url
from daras_ai_v2.field_render import field_desc, field_title, field_title_desc
from daras_ai_v2.functional import flatapply_parallel
from daras_ai_v2.glossary import validate_glossary_document
from daras_ai_v2.integrations_tab import render_integrations_tab
from daras_ai_v2.language_filters import (
    asr_languages_without_dialects,
    language_filter_selector,
    tts_languages_without_dialects,
)
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_SYSTEM,
    CHATML_ROLE_USER,
    SUPERSCRIPT,
    ConversationEntry,
    calc_appx_tokens,
    format_chat_entry,
    get_entry_text,
    run_language_model,
)
from daras_ai_v2.language_model_openai_audio import is_realtime_audio_url
from daras_ai_v2.language_model_settings_widgets import (
    LanguageModelSettings,
    language_model_selector,
    language_model_settings,
)
from daras_ai_v2.lipsync_api import LipsyncModel, LipsyncSettings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import HttpUrlStr, OptionalHttpUrlStr
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.search_ref import (
    CitationStyles,
    apply_response_formattings_prefix,
    apply_response_formattings_suffix,
    parse_refs,
)
from daras_ai_v2.tab_spec import PaneSpec, RecipeView, TabSpec
from gooey_gui.types.recipe_top_bar_props import TopBarIntegration
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
from daras_ai_v2.web_widget_embed import (
    chat_widget_input_to_request_body,
    get_chat_widget_messages,
    load_chat_widget_lib,
)
from functions.base_llm_tool import (
    BaseLLMTool,
    get_tool_from_call,
    render_called_functions,
)
from functions.models import FunctionTrigger
from functions.workflow_tools import DynamicLLMToolLoader
from recipes.DocExtract import document_intelligence_settings
from recipes.DocSearch import get_top_k_references, references_as_prompt
from recipes.GoogleGPT import SearchReference
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage, TextToSpeechSettings
from recipes.VideoBots import VideoBotsPage
from url_shortener.models import ShortenedURL
from usage_costs.twilio_usage_cost import (
    get_ivr_price_credits_and_seconds,
    get_non_ivr_price_credits,
)
from widgets.switch_with_section import switch_with_section
from widgets.workflow_bulk_runs_list import render_workflow_bulk_runs_list

GRAYCOLOR = "#00000073"
DEFAULT_TRANSLATION_MODEL = TranslationModels.google.name

SAFETY_BUFFER = 100


# The "Model <selector>" row above the instructions editor.
MODEL_ROW_CSS = """
/* app.css gives `.gui-input` a `margin-bottom: .9rem` meant for stacked form fields; on a
   one-line row it just pushes the editor down. Scoped rather than changed on the widget:
   `.<hash> .gui-input` outranks a bare `.gui-input`, so it needs no `!important` and leaks
   nowhere. */
& .gui-input {
    margin-bottom: 0;
}

/* Match the pane strip's pills (PANE_STRIP_CSS: 0.875rem). Neither react-select nor
   `AIModelSpec.display_html()` sets a font size, so the control was inheriting the page's 1rem
   and reading a size larger than the tabs directly above it. Set on the wrapper so the value,
   the placeholder and the open menu all shift together. */
& .gui-input-select {
    font-size: 0.875rem;
}

/* ...and the pills' 10px corners. `gui.selectbox` renders react-select with no
   `classNamePrefix`, so its control has only emotion-generated classes (`css-xxxxx-control`) -
   hence the attribute match on the one stable part of that name. Scoped under two classes, so
   it outranks emotion's own single-class rule without `!important`.
   If we end up restyling selects in more than this one place, the better fix is to add
   `classNamePrefix` in GooeySelect.tsx and target `.gooey-select__control` everywhere. */
& .gui-input-select [class*="-control"] {
    border-radius: 10px;
}
"""


# `(str, Enum)` rather than `enum.StrEnum`: this runs on 3.10, where StrEnum does not exist.
# Matching `BulkRunnerRunState` in gooey_gui/types/bulk_progress_props.py.
class ConfigPane(str, Enum):
    """Stable ids for the working column's panes.

    These are what session state and the About cards' deep links carry, so they must not
    change; the labels beside them in `_config_panes()` are display-only and can.
    """

    llm_instructions = "llm-instructions"
    knowledge = "knowledge"
    tools = "tools"
    settings = "settings"
    deploy = "deploy"
    debug = "debug"


class ReplyButton(typing_extensions.TypedDict):
    id: str
    title: str


class VideoBotsPageV2(BasePage):
    @classmethod
    def get_runner_page_cls(cls):
        return VideoBotsPage

    PROFIT_CREDITS = 3

    title = "Agent"  # "Create Interactive Video Bots"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/8c014530-88d4-11ee-aac9-02420a00016b/Copilot.png.png"
    workflow = Workflow.VIDEO_BOTS
    slug_versions = ["video-bots", "bots", "copilot", "agent"]

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
        input_prompt: str | None = Field(
            None,
            title="Input Prompt",
            description="The text message / prompt sent to the agent by the user",
        )
        input_audio: str | None = Field(
            None,
            title="Input Audio",
            description="The audio message sent to the agent by the user",
        )
        input_images: list[HttpUrlStr] | None = Field(
            None,
            title="Input Images",
            description="The images sent to the agent by the user",
        )
        input_documents: list[HttpUrlStr] | None = Field(
            None,
            title="Input Documents",
            description="The documents sent to the agent by the user. Note: this is not the same as the knowledge base documents.",
        )

        doc_extract_url: str | None = Field(
            None,
            title="📚 Document Extract Workflow",
            description="Select a workflow to extract text from documents and images.",
        )

        # conversation history/context
        messages: list[dict] | None = None

        bot_script: str | None = Field(
            None,
            title="Instructions",
            description="The system prompt for the LLM. "
            "Use this to set the personality of your agent and provide instructions for the bot's behavior. "
            "Supports [Jinja](https://jinja.palletsprojects.com/en/stable/templates/) templating.",
        )

        # llm model
        selected_model: LLMMarker | None = None
        document_model: str | None = Field(
            None,
            title="🩻 Photo / Document Intelligence",
            description="Which document intelligence model should be used to extract text from photos and documents?",
        )

        # doc search
        task_instructions: str | None = Field(
            None,
            title="Search Instructions",
            description="How should the LLM interpret the results from your knowledge base?",
        )
        query_instructions: str | None = None
        keyword_instructions: str | None = None
        documents: list[HttpUrlStr] | None = Field(
            None,
            title="Knowledge Base",
            description="Add documents or links to give your agent a knowledge base. When asked a question, we'll search them to generate an answer with citations. [Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/curate-your-knowledge-base-documents)",
        )
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

        bulk_runs: list[str] | None = Field(
            None,
            title="Bulk Evaluation",
            description="Add a [bulk](https://gooey.ai/bulk-runner) workflow with your golden evaluation data to rate workflows on cost, speed and latency.",
        )

    class RequestModel(
        LipsyncSettings, TextToSpeechSettings, LanguageModelSettings, RequestModelBase
    ):
        pass

    class ResponseModel(BaseModel):
        final_prompt: list[ConversationEntry | dict] | str = []

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
        metrics: dict | None = None

    def run_v2(
        self,
        request: "VideoBotsPageV2.RequestModel",
        response: "VideoBotsPageV2.ResponseModel",
    ) -> typing.Iterator[str | None]:
        if request.tts_provider == TextToSpeechProviders.ELEVEN_LABS.name and not (
            self.is_current_user_paying() or self.is_current_user_admin()
        ):
            raise UserError(
                """
                Please purchase Gooey.AI credits to use ElevenLabs voices <a href="/account">here</a>.
                """
            )

        try:
            llm_model = AIModelSpec.objects.get(name=request.selected_model)
        except AIModelSpec.DoesNotExist:
            raise UserError(
                f"Model {request.selected_model} not found. Should be one of: "
                + ", ".join(
                    AIModelSpec.objects.filter(category=AIModelSpec.Categories.llm)
                    .order_for_frontend()
                    .values_list("name", flat=True)
                )
            )
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

        tools_by_name = self.get_current_llm_tools()

        yield from self.build_final_prompt(
            request=request,
            response=response,
            user_input=user_input,
            model=llm_model,
            tools_by_name=tools_by_name,
            # use LLM audio input capability if not using a dedicated ASR model
            include_input_audio=(
                not asr_msg and not is_realtime_audio_url(request.input_audio)
            ),
        )

        yield from self.llm_loop(
            request=request,
            response=response,
            model=llm_model,
            asr_msg=asr_msg,
            tools_by_name=tools_by_name,
        )

        yield from self.tts_step(model=llm_model, request=request, response=response)

        yield from self.lipsync_step(request, response)

    def document_understanding_step(self, request):
        ocr_texts = []
        if request.input_images and (
            request.document_model
            or not AIModelSpec.objects.get(
                name=request.selected_model
            ).llm_is_vision_model
        ):
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
                    document_model=request.document_model,
                )
                if isinstance(pages, pd.DataFrame):
                    ocr_texts.append(pages.to_csv(index=False))
                elif len(pages) <= 1:
                    ocr_texts.append("\n\n---\n\n".join(pages))
                else:
                    ocr_texts.append(json.dumps(pages))
        return ocr_texts

    def asr_step(self, model, request, response, user_input):
        if (
            not request.input_audio
            or is_realtime_audio_url(request.input_audio)
            or (model.llm_supports_input_audio and not request.asr_model)
        ):
            # unless an ASR model is explicitly specified,
            # have the audio-enabled LLM accept the audio directly
            return None, user_input
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
        asr_msg = f'🎧: "{str(asr_output).rstrip()}"'
        response.output_text = [asr_msg] * request.num_outputs
        user_input = f"{asr_output}\n\n{user_input}".strip()
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
            user_input = f"Extracted Text: {text!r}\n\n{user_input}"
        return user_input

    def build_final_prompt(
        self, request, response, user_input, model, tools_by_name, include_input_audio
    ):
        # construct the system prompt
        bot_script = (request.bot_script or "").strip()
        if bot_script:
            variables = gui.session_state.get("variables") or {}
            for tool_name in tools_by_name:
                variables.pop(tool_name, None)
            bot_script = render_prompt_vars(
                bot_script, gui.session_state | tools_by_name
            )
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
            input_audio=include_input_audio and request.input_audio,
            input_documents=request.input_documents,
        )
        # truncate the history to fit the model's max tokens
        max_history_tokens = (
            model.llm_context_window
            - calc_appx_tokens(filter(None, [system_prompt, user_input]))
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
        max_allowed_tokens = model.llm_context_window - calc_appx_tokens(
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
            clip_idx = convo_window_clipper(query_msgs, model.llm_context_window // 2)
            query_msgs = query_msgs[clip_idx:]

            chat_history = messages_as_prompt(query_msgs)

            query_instructions = (request.query_instructions or "").strip()
            if query_instructions:
                yield "Creating search query..."
                search_query_raw = generate_final_search_query(
                    request=request,
                    response=response,
                    instructions=query_instructions,
                    context={"messages": chat_history},
                    response_format_type="json_object",
                ).strip()
                try:
                    search_query_parsed = json.loads(search_query_raw)
                except json.JSONDecodeError:
                    search_query_parsed = search_query_raw
                if isinstance(search_query_parsed, dict):
                    search_query_parsed = ", ".join(
                        map(str, filter(None, search_query_parsed.values()))
                    )
                if search_query_parsed:
                    response.final_search_query = str(search_query_parsed)
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
                k_request.selected_model = "gpt_4_o"
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

    def __init__(self, *args, **kwargs):
        self.active_tool_names = set()
        super().__init__(*args, **kwargs)

    def llm_loop(
        self,
        *,
        request: "VideoBotsPageV2.RequestModel",
        response: "VideoBotsPageV2.ResponseModel",
        model: AIModelSpec,
        asr_msg: str | None = None,
        prev_output_text: list[str] | None = None,
        tools_by_name: dict[str, BaseLLMTool],
    ) -> typing.Iterator[str | None]:
        from functions.gooey_builder_tools import get_current_builder_tools

        yield f"Summarizing with {model.label}..."

        audio_session_extra = None
        if model.llm_is_audio_model:
            audio_session_extra = {}
            if request.openai_voice_name:
                audio_session_extra["voice"] = request.openai_voice_name

        tools_by_name |= get_current_builder_tools(self.current_sr)

        loader = DynamicLLMToolLoader(tools_by_name, self.active_tool_names)
        tools_by_name[loader.name] = loader
        active_tools = [
            tool for tool in tools_by_name.values() if loader.is_tool_active(tool)
        ]
        response.final_prompt[0]["tools"] = [
            tool.spec_function for tool in active_tools
        ]

        chunks: typing.Generator[list[dict], None, None] = run_language_model(
            model=model.name,
            messages=response.final_prompt,
            max_tokens=request.max_tokens,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
            response_format_type=request.response_format_type,
            reasoning_effort=request.reasoning_effort,
            tools=active_tools,
            stream=True,
            audio_url=request.input_audio,
            audio_session_extra=audio_session_extra,
        )

        tool_calls = None
        output_text = None
        response.final_prompt.append({"role": CHATML_ROLE_ASSISTANT, "content": ""})

        for i, choices in enumerate(chunks):
            if not choices:
                continue

            metrics = choices[0].get("metrics")
            if metrics:
                response.metrics = metrics

            output_text = [
                "\n\n".join(filter(None, (prev_text, entry.get("content"))))
                for prev_text, entry in zip_longest(
                    (prev_output_text or []), choices, fillvalue=""
                )
            ]
            response.final_prompt[-1]["content"] = choices[0]["content"] or ""

            tool_calls = choices[0].get("tool_calls")
            if tool_calls:
                for call in tool_calls:
                    tool = tools_by_name[call["function"]["name"]]
                    call["label"] = tool.label
                    call["icon"] = tool.get_icon()
                response.final_prompt[-1]["tool_calls"] = tool_calls

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
                yield f"Streaming{str(i + 1).translate(SUPERSCRIPT)} {model.label}..."

        if response.output_text:
            response.output_text = [text.strip() for text in response.output_text]

        if not tool_calls:
            return
        for call in tool_calls:
            tool, arguments = get_tool_from_call(call["function"], tools_by_name)
            if not arguments:
                continue
            yield f"🛠 {tool.label}..."
            try:
                output = tool.call_json(arguments)
            except Exception as e:
                output = json.dumps(dict(error=str(e)))
                error_type = getattr(e, "error_type", type(e).__name__)
                if error_type and exceptions.get_error_renderer(error_type):
                    # bubble up error so the parent run's standard error pipeline renders it
                    raise
                else:
                    traceback.print_exc()
                    sentry_sdk.capture_exception(e)
            finally:
                response.final_prompt.append(
                    dict(
                        role="tool",
                        content=output,
                        tool_call_id=call["id"],
                        run_url=tool.get_url(),
                    ),
                )

        yield from self.llm_loop(
            request=request,
            response=response,
            model=model,
            prev_output_text=output_text,
            tools_by_name=tools_by_name,
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
            tts_source = [
                "".join(snippet for snippet, _ in parse_refs(text, response.references))
                for text in output_text
            ]
            response.raw_tts_text = tts_source
        else:
            tts_source = output_text

        # remove html tags from the output text for tts
        raw_tts_text = [parse_bot_html(text)[1].strip() for text in tts_source]
        if raw_tts_text != output_text:
            response.raw_tts_text = raw_tts_text

        return output_text

    def tts_step(self, model, request, response):
        if request.tts_provider and not model.llm_is_audio_model:
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

    def speech_recognition_settings(self):
        with gui.div(className="pt-2 ps-1"):
            gui.caption(field_desc(self.RequestModel, "user_language"))

            # drop down to filter models based on the selected language
            selected_filter_language = language_filter_selector(
                options=asr_languages_without_dialects(),
                key="asr_language_filter",
            )

            col1, col2 = gui.columns(2)
            with col1:
                asr_model = asr_model_selector(
                    key="asr_model",
                    language_filter=selected_filter_language,
                    label=f"###### {field_title(self.RequestModel, 'asr_model')}",
                    format_func=lambda x: (AsrModels[x].value if x else "Auto Select"),
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

            if asr_model and asr_model.supports_input_prompt():
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
            gui.div(className="pb-1")

    def text_to_speech_settings(self):
        with gui.div(className="pt-2 ps-1"):
            selected_filter_language = language_filter_selector(
                options=tts_languages_without_dialects(),
                key="tts_language_filter",
            )
            text_to_speech_provider_selector(
                self, language_filter=selected_filter_language
            )

        gui.newline()

        if gui.checkbox(
            label="**🫦 Add Lipsync Video**",
            value=bool(gui.session_state.get("input_face")),
        ):
            self.lipsync_settings()
        else:
            gui.session_state["input_face"] = None
            gui.session_state.pop("lipsync_model", None)

        gui.div(className="pb-1")

    def lipsync_settings(self):
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

    def document_intelligence_settings(self):
        with gui.div(className="pt-2 ps-1"):
            document_intelligence_settings(
                title=f"{field_desc(self.RequestModel, 'document_model')}",
            )

    def validate_form_v2(self):
        input_glossary = gui.session_state.get("input_glossary_document", "")
        output_glossary = gui.session_state.get("output_glossary_document", "")
        if input_glossary:
            validate_glossary_document(input_glossary)
        if output_glossary:
            validate_glossary_document(output_glossary)

    def render_usage_guide(self):
        youtube_video("4wGKQAGUm48")

    def render_settings(self):
        tts_provider = gui.session_state.get("tts_provider")
        if tts_provider:
            text_to_speech_settings(self, tts_provider)
            gui.write("---")

        lipsync_model = gui.session_state.get("lipsync_model")
        if lipsync_model and gui.session_state.get("input_face"):
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
                help="[Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/advanced-settings#fine-tuned-language-understanding-with-custom-glossaries) about how to super-charge your agent's domain specific language understanding!",
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
                "###### 👩‍🏫 " + field_title(self.RequestModel, "task_instructions"),
                help=field_desc(self.RequestModel, "task_instructions"),
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
        from daras_ai_v2.bots import parse_bot_html

        input_prompt = state.get("input_prompt") or state.get("raw_input_text")
        if input_prompt:
            with (
                gui.div(className="d-flex justify-content-end mb-1"),
                gui.div(
                    className="bg-light rounded-3 text-dark p-2",
                    style=dict(maxWidth="85%"),
                ),
            ):
                gui.write(
                    truncate_text_words(input_prompt, maxlen=200),
                    className="container-margin-reset",
                )

        output_video = state.get("output_video")
        output_text = state.get("output_text")
        output_audio = state.get("output_audio")
        if not (output_text or output_video or output_audio):
            return

        with gui.div(style=dict(width="85%"), className="pt-3"):
            if output_video:
                gui.video(output_video[0], autoplay=True)

            if output_audio:
                gui.audio(output_audio[0])

            if output_text:
                with (
                    gui.div(
                        className="border rounded-3 p-2",
                        style=dict(borderColor="#f0f0f0"),
                    ),
                    gui.styled("""
                        & {
                            max-height: 4.5em; /* ~3 lines with 1.5 line-height */
                            overflow: hidden;
                            display: -webkit-box;
                            -webkit-line-clamp: 3;
                            -webkit-box-orient: vertical;
                            line-height: 1.5;
                        }
                    """),
                ):
                    text = parse_bot_html(output_text[0])[1]
                    gui.write(text, className="container-margin-reset")

    scroll_into_view = False

    def _render_running_output(self):
        # The embedded widget renders its own running state. Do not call scrollIntoView:
        # the v2 app shell keeps its header outside the body scroller.
        return

    def render_output(self):
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
                self.on_send(input_data)

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

        messages = get_chat_widget_messages(gui.session_state)

        # fill branding with bot integration data if available
        bot_integration = (
            BotIntegration.objects.filter(
                published_run=self.current_pr,
                platform=Platform.WEB,
            )
            .order_by("-updated_at")
            .first()
        )
        if bot_integration:
            bot_branding = bot_integration.get_web_widget_branding()
        else:
            bot_branding = dict(
                name=self.current_pr.title,
                title=self.current_pr.title,
            )
        if self.current_pr.photo_url:
            bot_branding["photoUrl"] = self.current_pr.photo_url
        bot_branding["showPoweredByGooey"] = False

        config = dict(
            integration_id="magic",
            target="#gooey-embed",
            mode="inline",
            enableAudioMessage=True,
            enablePhotoUpload=True,
            enableConversations=True,
            showToolCalls=True,
            branding=bot_branding,
            fillParent=True,
            enableSourcePreview=False,
            secrets=dict(GOOGLE_MAPS_API_KEY=settings.GOOGLE_MAPS_API_KEY),
        )
        # the page's own top bar already names the agent, so the widget never needs its own
        config["showHeader"] = False
        if self._has_whatsapp_integration:
            config["theme"] = "whatsapp"
        if settings.DEBUG:
            from routers.bots_api import stream_create

            config["apiUrl"] = get_api_route_url(stream_create)

        gui.div(
            # fill the scrolling body area, not the viewport: the top bar sits above this,
            # so `100vh` would overflow by exactly the bar's height
            style=dict(height="100%", minHeight=0),
            id="gooey-embed",
        )
        # Owns the widget's teardown when this preview disappears or a different workflow
        # replaces it client-side.
        gui.component(
            "GooeyEmbedTeardown",
            embed_key=str(self.current_pr.published_run_id),
        )
        load_chat_widget_lib()
        gui.js(
            """
async function loadGooeyEmbed() {
    await window.waitUntilHydrated;
    let embedTarget = document.getElementById("gooey-embed");
    if (typeof GooeyEmbed === "undefined" || !embedTarget || embedTarget.children.length) {
        return;
    }
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
        fetchConversations: () => gui.fetchServerAPI("/__/agent/fetch-conversations", { run_url }),
    };
    GooeyEmbed.copilotPreviewControl = controller;
    GooeyEmbed.mount(config, controller);
}

const script = document.getElementById("gooey-embed-script");
if (script) script.onload = loadGooeyEmbed;
loadGooeyEmbed();
window.addEventListener("hydrated", loadGooeyEmbed);
// once the widget is already mounted, update the messages and branding to latest
if (typeof GooeyEmbed !== "undefined" && GooeyEmbed.copilotPreviewControl) {
    GooeyEmbed.copilotPreviewControl.setMessages?.(messages);
    GooeyEmbed.copilotPreviewControl.updateConfig?.({
        theme: config.theme,
        branding: config.branding,
        showHeader: config.showHeader,
    });
}
            """,
            config=config,
            messages=messages,
            run_url=str(self.request.url),
        )

    @cached_property
    def _has_whatsapp_integration(self) -> bool:
        return BotIntegration.objects.filter(
            published_run=self.current_pr,
            platform=Platform.WHATSAPP,
        ).exists()

    def on_send(self, input_data: dict):
        request_body, message_thread = chat_widget_input_to_request_body(
            self.current_sr, gui.session_state, input_data
        )
        gui.session_state.update(request_body)
        self.submit_and_redirect(message_thread=message_thread)

    def _render_regenerate_button(self):
        pass

    def render_steps(self):
        if gui.session_state.get("tts_provider"):
            gui.video(gui.session_state.get("input_face"), caption="Input Face")

        final_search_query = gui.session_state.get("final_search_query")
        if final_search_query:
            gui.text_area(
                "###### `search_query`",
                value=str(final_search_query),
                disabled=True,
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

        final_prompt = gui.session_state.get("final_prompt")
        if final_prompt:
            if isinstance(final_prompt, str):
                text_output("###### `final_prompt`", value=final_prompt, height=300)
            else:
                gui.write(
                    f"###### {icons.terminal} `final_prompt`",
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
        total = get_non_ivr_price_credits(self.current_sr) + self.PROFIT_CREDITS

        if state.get("tts_provider") == TextToSpeechProviders.ELEVEN_LABS.name:
            output_text_list = state.get("raw_tts_text") or state.get(
                "raw_output_text", []
            )
            tts_state = {"text_prompt": "".join(output_text_list)}
            total += TextToSpeechPage().get_raw_price(tts_state)

        if state.get("selected_model") == "agrillm_qwen3_30b":
            total += 100

        if is_realtime_audio_url(state.get("input_audio")):
            total += get_ivr_price_credits_and_seconds(self.current_sr)[0]

        if state.get("input_face"):
            total += 1

        return total

    def additional_notes(self):
        llm_cost = get_non_ivr_price_credits(self.current_sr)

        try:
            model = AIModelSpec.objects.get(
                name=gui.session_state.get("selected_model")
            )
            if model.name == "agrillm_qwen3_30b":
                llm_cost += 100
            label = model.label
        except AIModelSpec.DoesNotExist:
            label = "LLM"

        notes = (
            f"\nBreakdown: {math.ceil(llm_cost)} ({label}) + {self.PROFIT_CREDITS}/run"
        )

        if (
            gui.session_state.get("tts_provider")
            == TextToSpeechProviders.ELEVEN_LABS.name
        ):
            notes += f" *+ {TextToSpeechPage().get_cost_note()} (11labs)*"

        if is_realtime_audio_url(gui.session_state.get("input_audio")):
            credits, duration_sec = get_ivr_price_credits_and_seconds(self.current_sr)
            if credits:
                duration_min = math.ceil(int(duration_sec) / 60)
                notes += f" + {credits} ({duration_min}min call)"

        if gui.session_state.get("input_face"):
            notes += " + 1 (lipsync)"

        return notes

    DEMO_ACTION_PREFIX = "demo:"

    def _top_bar_integrations(self) -> list[TopBarIntegration]:
        """v1's demo buttons, as chips in the top bar.

        They open a dialog rather than navigating, so each carries an action key instead of
        an href and comes back through the bar's menu key.
        """
        from widgets.demo_button import get_demo_bots

        integrations = []
        for bi_id, platform_id in get_demo_bots(self.current_pr):
            platform = Platform(platform_id)
            integrations.append(
                TopBarIntegration(
                    # the chip opens a demo of the live bot, so it says so - v1 could get away
                    # with a bare platform name because its buttons sat under a "Demos" header
                    label=f"Try in {platform.get_title()}",
                    icon=platform.get_icon(),
                    color=platform.get_demo_button_color() or None,
                    key=f"{self.DEMO_ACTION_PREFIX}{bi_id}",
                )
            )
        return integrations

    def _handle_top_bar_actions(self):
        super()._handle_top_bar_actions()

        from widgets.demo_button import get_demo_bots, render_demo_dialog

        picked = gui.session_state.pop(self.TOP_BAR_MENU_KEY, None)
        for bi_id, _ in get_demo_bots(self.current_pr):
            # the dialog has to be re-entered on every pass while it is open, so this runs
            # for each demo bot rather than only the one just clicked
            ref = gui.use_alert_dialog(key=f"demo-modal-{bi_id}")
            if picked == f"{self.DEMO_ACTION_PREFIX}{bi_id}":
                ref.set_open(True)
            if ref.is_open:
                render_demo_dialog(ref, bi_id)

    def render_header_extra(self):
        # v2 surfaces the demo buttons as chips in the top bar instead
        pass

    def entry_tab_slug(self, tabs: list[TabSpec]) -> RecipeView:
        """Show About to a first-time visitor and Split to everyone else.

        Someone who has arrived at a workflow they do not own wants to know what it is
        before they meet its knobs; someone opening their own run wants to work.
        """
        return RecipeView.about if self.is_unowned_example() else RecipeView.split

    def get_tab_spec(self) -> list[TabSpec]:
        """The agent tab set.

        Deploy is deliberately absent: it becomes a sub-tab of Config in a later slice, and
        until then its body stays reachable through v1's `/integrations/` url via
        `render_selected_tab()`.
        """
        if self.is_unowned_example():
            return self.get_viewer_tab_spec()
        return [
            TabSpec(
                slug=RecipeView.about,
                label="About",
                icon=icons.info,
            ),
            TabSpec(
                slug=RecipeView.edit,
                label="Edit",
                icon=icons.edit,
            ),
            TabSpec(
                slug=RecipeView.preview,
                label="Preview",
                icon=icons.preview,
                # Not immersive on a phone any more. It used to take the whole screen, which
                # meant hiding the top bar and giving the pane a floating back pill of its own
                # to make up for it. The bar is the app's only header now, and the design keeps
                # it on every screen - so the pane keeps the header, and the header's back
                # arrow is the way out. One piece of chrome instead of two.
            ),
            TabSpec(
                slug=RecipeView.split,
                label="Split",
                icon=icons.split,
                # two columns side by side - there is no room for it on a phone
                desktop_only=True,
            ),
        ]

    CONFIG_PANE_KEY = "--config-subtab"

    def _render_about_meta(self):
        """How this agent is put together: its model, what it knows, what it can do.

        Each card is a way into the Config pane that owns the setting, so About reads as a
        summary you can act on rather than a dead-end description.
        """
        model = self._about_model_summary()

        # Knowledge and Tools read as one idea - what the agent can reach outside itself -
        # so they share a group, leaving the model on its own as the thing it *is*.
        integrations: list[tuple[str, str, ConfigPane]] = []
        if documents := len(gui.session_state.get("documents") or []):
            plural = "" if documents == 1 else "s"
            integrations.append(
                (icons.library, f"{documents} document{plural}", ConfigPane.knowledge)
            )
        if tools := len(gui.session_state.get("functions") or []):
            plural = "" if tools == 1 else "s"
            integrations.append((icons.code, f"{tools} tool{plural}", ConfigPane.tools))

        # a row of zeroes says less than no row: skip the heading too, not just the cards
        if not model and not integrations:
            return

        with gui.div(className="v2-about-groups"):
            if model:
                self._render_about_meta_group(
                    "Model", [(*model, ConfigPane.llm_instructions)]
                )
            if integrations:
                self._render_about_meta_group("Tools & Integrations", integrations)

    def _render_about_meta_group(
        self, title: str, cards: list[tuple[str, str, ConfigPane]]
    ):
        with gui.div(className="v2-about-group"):
            gui.html(f'<div class="v2-about-section-title">{html.escape(title)}</div>')
            with gui.div(className="v2-about-meta"):
                for icon, label, pane in cards:
                    self._render_about_meta_card(icon=icon, label=label, pane=pane)

    def _about_model_summary(self) -> tuple[str, str] | None:
        """(icon html, label) for the selected LLM, or None if the run has not picked one."""
        name = gui.session_state.get("selected_model")
        if not name:
            return None
        spec = AIModelSpec.objects.filter(name=name).select_related("creator").first()
        if not spec:
            # a model that has since been removed - its name is still better than nothing
            return icons.sparkles, name
        return (spec.creator and spec.creator.html_icon()) or icons.sparkles, spec.label

    def _render_about_meta_card(self, *, icon: str, label: str, pane: ConfigPane):
        with gui.component(
            "RecipeWorkspaceTrigger",
            storage_key=self._workspace_storage_key(),
            initial_view=self.entry_tab_slug(self.get_tab_spec()),
            view=RecipeView.edit,
            state_key=self.CONFIG_PANE_KEY,
            state_value=pane,
            className="v2-about-meta-card",
        ):
            # icon over label, and no chevron: the whole card is the link, so an affordance
            # arrow only competed with the icon for the eye
            gui.html(
                f'<span class="v2-about-meta-icon">{icon}</span>'
                f'<span class="v2-about-meta-label">{html.escape(label)}</span>'
            )

    def _editor_wants_full_width(self) -> bool:
        """Deploy is a wide configuration surface that carries its own web preview, so
        pairing it with the chat preview leaves both cramped. It takes the full width
        instead, and the controls that would pair it back up go with it.
        """
        return gui.session_state.get(self.CONFIG_PANE_KEY) == ConfigPane.deploy

    def _render_split_tab(self):
        """Split is two columns, except where the open pane has claimed the row."""
        if self._editor_wants_full_width():
            # one column of 12 rather than no column at all, so the full-width pane keeps
            # the same gutters as the two-column layout. No submit row here to redirect on.
            self._render_solo_input_col()
            return
        super()._render_split_tab()

    def _config_panes(self) -> list[PaneSpec]:
        """The working column's panes, in strip order.

        These regroup what v1 spread across `render_form_v2` and the Settings expander -
        every pane composes existing widgets, none of them reimplement anything.
        """
        return [
            PaneSpec(
                ConfigPane.llm_instructions,
                "LLM Instructions",
                self._render_llm_instructions_pane,
            ),
            PaneSpec(ConfigPane.knowledge, "Knowledge", self._render_knowledge_pane),
            # functions only - the variables half of v1's block moved to a dialog beside the
            # prompt. Rendering it here too would mean two editors on the same widget keys.
            PaneSpec(ConfigPane.tools, "Tools", self._render_functions),
            PaneSpec(ConfigPane.settings, "Settings", self._render_settings_pane),
            PaneSpec(ConfigPane.deploy, "Deploy", self._render_deploy_panel),
            PaneSpec(ConfigPane.debug, "Debug", self._render_debug_pane),
        ]

    def _render_input_col(self):
        """The working column, shared by Config (alone) and Split (beside the preview).

        Overriding this - rather than the tabs - is what gives both of them the pane strip
        without duplicating the layout.
        """
        with gui.div(className="d-flex flex-column h-100", style=dict(minHeight=0)):
            # strip and submit row are fixed; only the pane between them scrolls, and only
            # when its content actually overflows
            render_pane = self._render_pane_strip(
                self._config_panes(), key=self.CONFIG_PANE_KEY
            )
            with gui.div(
                # pe-3 keeps the scrollbar off the content when the pane overflows
                className="flex-grow-1 overflow-auto pt-2 pe-1 pe-lg-3",
                style=dict(minHeight=0),
            ):
                render_pane()

        # nothing in this column submits any more; the top bar owns Run
        return False

    def _render_variables_button(self):
        """Variables live beside the prompt that references them, not on a pane of their own.

        The editor is a list of name/value rows that would crowd this pane and steal height
        from the instructions, so the button carries the count and the editing happens in a
        dialog. The count comes from `variable_names()`, which reads the prompt directly -
        so it is right even before the editor has ever been opened.
        """
        ref = gui.use_alert_dialog(key="variables-modal")
        # "(0)" reads as a broken counter rather than an empty list, so it is left off
        count = len(self.variable_names())
        if gui.button(
            f"{icons.variables} Variables" + (f" ({count})" if count else ""),
            type="tertiary",
            # ms-auto pushes it to the far end of the row, opposite the model selector.
            # fw-normal + small because `.btn.btn-theme` is bold at body size, and a
            # secondary action next to a form field should not shout louder than the field's
            # own label.
            className="mb-0 p-2 text-nowrap ms-auto fw-normal small",
            key="open-variables",
        ):
            ref.set_open(True)
        if not ref.is_open:
            return

        with (
            gui.alert_dialog(ref=ref, modal_title="#### Variables", large=True),
            gui.styled(VARIABLES_DIALOG_CSS),
            gui.div(),
        ):
            # kept whether or not any exist: the editor never says where variables come
            # from, and most are declared by writing them into the prompt, not added here
            with gui.div(className="container-margin-reset mb-3"):
                gui.caption(
                    "Variables let you pass custom parameters into this agent.  \n"
                    "Reference one in your instructions with Jinja - "
                    "`{{ my_variable }}` - and it appears here to fill in. "
                    "[Learn more](/variables-help)."
                )
            self._render_variables_editor(heading=False)

    def _render_llm_instructions_pane(self):
        """Model selector pinned on top, editor filling whatever height is left.

        v1 capped the editor at `maxHeight: 50vh`, which in an app shell leaves dead space
        below it on tall screens and still overflows on short ones.
        """
        with gui.div(className="d-flex flex-column h-100", style=dict(minHeight=0)):
            # a compact row - small label left, selector right - rather than v1's full-width
            # heading and field, so the editor gets the height instead.
            with (
                gui.styled(MODEL_ROW_CSS),
                gui.div(className="d-flex align-items-center gap-3 mb-2 flex-shrink-0"),
            ):
                gui.html('<span class="text-muted small">Model</span>')
                # a fixed width rather than a percentage: the selector holds one model name,
                # so it should not keep growing with the pane. Capped as a share of the pane
                # too, so it still fits when the Builder squeezes the column.
                with gui.div(
                    style=dict(width="14rem", maxWidth="45%"), className="m-0"
                ):
                    language_model_selector(label="")
                self._render_variables_button()

            with (
                gui.styled(FILL_HEIGHT_EDITOR_CSS),
                gui.div(
                    className="flex-grow-1 d-flex flex-column", style=dict(minHeight=0)
                ),
            ):
                gui.code_editor(
                    label="",
                    key="bot_script",
                    language="jinja",
                    help=field_desc(self.RequestModel, "bot_script"),
                )

    def _render_knowledge_pane(self):
        # v1 gated this on language_model_selector's RETURN VALUE, which only exists while
        # that widget renders. It lives on another pane now, so read the state key instead -
        # otherwise the uploader silently disappears unless LLM Instructions rendered first.
        if not AIModelSpec.objects.filter(
            name=gui.session_state.get("selected_model"), llm_is_audio_model=True
        ).exists():
            bulk_documents_uploader(
                label=(
                    f"#### {icons.books} " + field_title(self.RequestModel, "documents")
                ),
                accept=["audio/*", "application/*", "video/*", "text/*"],
                help=field_desc(self.RequestModel, "documents"),
            )

        if not gui.session_state.get("documents"):
            return

        gui.write("#### 📄 Knowledge Base")
        gui.text_area(
            "###### 👩‍🏫 " + field_title(self.RequestModel, "task_instructions"),
            help=field_desc(self.RequestModel, "task_instructions"),
            key="task_instructions",
            height=300,
        )
        citation_style_selector()
        gui.checkbox("🔗 Shorten citation links", key="use_url_shortener")
        cache_knowledge_widget(self)
        doc_extract_selector(self.request.user)

        gui.write("---")
        query_instructions_widget()
        keyword_instructions_widget()
        gui.write("---")
        doc_search_advanced_settings()

    def _render_settings_pane(self):
        gui.markdown("#### 💪 Capabilities")

        speech_recognition_enabled = switch_with_section(
            label="##### 🦻 Speech Recognition & Translation",
            key="_speech_recognition_enabled",
            control_keys=["user_language", "asr_model"],
            render_section=self.speech_recognition_settings,
        )
        if not speech_recognition_enabled:
            gui.session_state["asr_model"] = None
            gui.session_state["asr_language"] = None
            gui.session_state["asr_prompt"] = None
            gui.session_state["asr_task"] = None
            gui.session_state["translation_model"] = None
            gui.session_state["user_language"] = None

        text_to_speech_enabled = switch_with_section(
            label="##### 🗣️ Text to Speech & Lipsync",
            key="_text_to_speech_enabled",
            control_keys=["tts_provider"],
            render_section=self.text_to_speech_settings,
        )
        if not text_to_speech_enabled:
            gui.session_state["tts_provider"] = None

        document_intelligence_enabled = switch_with_section(
            label="##### 🩻 Photo & Document Intelligence",
            key="_document_intelligence_enabled",
            control_keys=["document_model"],
            render_section=self.document_intelligence_settings,
        )
        if not document_intelligence_enabled:
            gui.session_state["document_model"] = None

        switch_with_section(
            label="##### 📊 Analytics & Evaluation",
            control_keys=["bulk_runs"],
            render_section=lambda: render_workflow_bulk_runs_list(
                user=self.request.user,
                workspace=self.request.user and self.current_workspace,
                sr=self.current_sr,
                pr=self.current_pr,
            ),
        )

        gui.write("---")
        self.render_settings()

    def _render_debug_pane(self):
        render_called_functions(saved_run=self.current_sr, trigger=FunctionTrigger.pre)
        self.render_steps()
        render_called_functions(saved_run=self.current_sr, trigger=FunctionTrigger.post)
        gui.caption(
            f"""
            Run Time: {self.current_sr.run_time.total_seconds():.2f}s\n\n
            [Parent Run]({self.current_sr.parent and self.current_sr.parent.get_app_url()})
            """,
            unsafe_allow_html=True,
        )

    def _render_deploy_panel(self):
        """Deploy's body. Reached two ways - the Config sub-tab, and v1's `/integrations/`
        deep link via `render_selected_tab()` - so it lives in exactly one place.
        """
        user = self.request.user
        # not signed in case
        if not user or user.is_anonymous:
            integrations_welcome_screen(title="Connect your Agent")
            gui.newline()
            with gui.center():
                gui.anchor("Get Started", href=self.get_auth_url(), type="primary")
            return
        sr, pr = self.current_sr_pr
        render_integrations_tab(
            user=self.request.user,
            workspace=self.current_workspace,
            saved_run=sr,
            published_run=pr,
        )

    def render_selected_tab(self):
        if self.tab == RecipeTabs.integrations:
            self._render_deploy_panel()
        else:
            super().render_selected_tab()

    def create_new_run(
        self,
        *,
        enable_rate_limits: bool = False,
        run_status: str | None = STARTING_STATE,
        **defaults,
    ) -> SavedRun:
        message_thread = defaults.pop("message_thread", None)
        if not _can_use_message_thread(message_thread, self.request.user):
            message_thread = None

        sr = super().create_new_run(
            enable_rate_limits=enable_rate_limits,
            run_status=run_status,
            message_thread=message_thread,
            **defaults,
        )

        if message_thread:
            if not message_thread.first_run:
                message_thread.first_run = sr
            message_thread.last_run = sr
            message_thread.save(update_fields=["first_run", "last_run"])
        else:
            message_thread = MessageThread.objects.create(
                title=gui.session_state.get("input_prompt") or "",
                first_run=sr,
                last_run=sr,
            )
            sr.message_thread = message_thread
            sr.save(update_fields=["message_thread"])

        return sr


def _can_use_message_thread(
    message_thread: MessageThread | None, user: AppUser | None
) -> bool:
    if not message_thread:
        return False

    if not user:
        return False

    for sr in (message_thread.first_run, message_thread.last_run):
        if sr and sr.uid != user.uid:
            return False

    return True


def messages_as_prompt(query_msgs: list[dict]) -> str:
    return "\n".join(
        f'{entry["role"]}: """{get_entry_text(entry)}"""' for entry in query_msgs
    )


def infer_asr_model_and_language(
    user_language: str, default=AsrModels.gpt_4_o_audio
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
        if calc_appx_tokens(window[i:]) > max_tokens:
            return i + step
    return 0
