import json
import mimetypes
import typing
import math

from django.db.models import QuerySet, Q, Sum
from furl import furl
from pydantic import BaseModel, Field

import gooey_ui as st
from usage_costs.models import UsageCost
from bots.models import BotIntegration, Platform, SavedRun
from bots.models import Workflow
from daras_ai.image_input import (
    truncate_text_words,
)
from daras_ai_v2.asr import (
    run_google_translate,
    google_translate_language_selector,
)
from daras_ai_v2.azure_doc_extract import (
    azure_form_recognizer,
    azure_form_recognizer_models,
)
from daras_ai_v2.base import BasePage, MenuTabs
from daras_ai_v2.bot_integration_widgets import (
    general_integration_settings,
    slack_specific_settings,
    broadcast_input,
    get_bot_test_link,
)
from daras_ai_v2.doc_search_settings_widgets import (
    query_instructions_widget,
    keyword_instructions_widget,
    doc_search_advanced_settings,
    doc_extract_selector,
    document_uploader,
    citation_style_selector,
)
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.field_render import field_title_desc, field_desc
from daras_ai_v2.functions import LLMTools
from daras_ai_v2.glossary import glossary_input, validate_glossary_document
from daras_ai_v2.language_model import (
    run_language_model,
    calc_gpt_tokens,
    ConversationEntry,
    LargeLanguageModels,
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    CHATML_ROLE_SYSTEM,
    model_max_tokens,
    get_entry_images,
    get_entry_text,
    format_chat_entry,
    SUPERSCRIPT,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.prompt_vars import render_prompt_vars, prompt_vars_widget
from daras_ai_v2.query_generator import generate_final_search_query
from daras_ai_v2.query_params import gooey_get_query_params
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
)
from daras_ai_v2.vector_search import DocSearchRequest
from recipes.DocSearch import (
    get_top_k_references,
    references_as_prompt,
)
from recipes.GoogleGPT import SearchReference
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage
from url_shortener.models import ShortenedURL

DEFAULT_COPILOT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f454d64a-9457-11ee-b6d5-02420a0001cb/Copilot.jpg.png"
INTEGRATION_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/c3ba2392-d6b9-11ee-a67b-6ace8d8c9501/image.png"
INSTAGRAM_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/3e7ebbb6-d6c8-11ee-a182-02420a000125/image.png"
FACEBOOK_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/4243ce22-d6db-11ee-8e6a-02420a000126/facebook.png"
SLACK_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ee8c5b1c-d6c8-11ee-b278-02420a000126/image.png"
WHATSAPP_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1e49ad50-d6c9-11ee-99c3-02420a000123/Digital_Inline_Green.png"
LANDBOT_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/3705ed24-d6db-11ee-a22a-02420a000125/landbot.png"
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
    title = "Copilot for your Enterprise"  # "Create Interactive Video Bots"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/8c014530-88d4-11ee-aac9-02420a00016b/Copilot.png.png"
    workflow = Workflow.VIDEO_BOTS
    slug_versions = ["video-bots", "bots", "copilot"]

    sane_defaults = {
        "messages": [],
        # tts
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.name,
        "google_voice_name": "en-IN-Wavenet-A",
        "google_pitch": 0.0,
        "google_speaking_rate": 1.0,
        "uberduck_voice_name": "Aiden Botha",
        "uberduck_speaking_rate": 1.0,
        "elevenlabs_voice_name": "Rachel",
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
    }

    class RequestModel(BaseModel):
        bot_script: str | None

        input_prompt: str
        input_images: list[str] | None
        input_documents: list[str] | None
        doc_extract_url: str | None = Field(
            title="📚 Document Extract Workflow",
            description="Select a workflow to extract text from documents and images.",
        )

        # conversation history/context
        messages: list[ConversationEntry] | None

        # tts settings
        tts_provider: (
            typing.Literal[tuple(e.name for e in TextToSpeechProviders)] | None
        )
        uberduck_voice_name: str | None
        uberduck_speaking_rate: float | None
        google_voice_name: str | None
        google_speaking_rate: float | None
        google_pitch: float | None
        bark_history_prompt: str | None
        elevenlabs_voice_name: str | None
        elevenlabs_api_key: str | None
        elevenlabs_voice_id: str | None
        elevenlabs_model: str | None
        elevenlabs_stability: float | None
        elevenlabs_similarity_boost: float | None
        azure_voice_name: str | None

        # llm settings
        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )
        document_model: str | None = Field(
            title="🩻 Photo / Document Intelligence",
            description="When your copilot users upload a photo or pdf, what kind of document are they mostly likely to upload? "
            "(via [Azure](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/use-sdk-rest-api?view=doc-intel-3.1.0&tabs=linux&pivots=programming-language-rest-api))",
        )
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        # lipsync
        input_face: str | None
        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

        # doc search
        task_instructions: str | None
        query_instructions: str | None
        keyword_instructions: str | None
        documents: list[str] | None
        max_references: int | None
        max_context_words: int | None
        scroll_jump: int | None

        embedding_model: typing.Literal[tuple(e.name for e in EmbeddingModels)] | None
        dense_weight: float | None = DocSearchRequest.__fields__[
            "dense_weight"
        ].field_info

        citation_style: typing.Literal[tuple(e.name for e in CitationStyles)] | None
        use_url_shortener: bool | None

        user_language: str | None = Field(
            title="🔠 User Language",
            description="Choose a language to translate incoming text & audio messages to English and responses back to your selected language. Useful for low-resource languages.",
        )
        # llm_language: str | None = "en" <-- implicit since this is hardcoded everywhere in the code base (from facebook and bots to slack and copilot etc.)
        input_glossary_document: str | None = Field(
            title="Input Glossary",
            description="""
Translation Glossary for User Langauge -> LLM Language (English)
            """,
        )
        output_glossary_document: str | None = Field(
            title="Output Glossary",
            description="""
Translation Glossary for LLM Language (English) -> User Langauge
            """,
        )

        variables: dict[str, typing.Any] | None

        tools: list[LLMTools] | None = Field(
            title="🛠️ Tools",
            description="Give your copilot superpowers by giving it access to tools. Powered by [Function calling](https://platform.openai.com/docs/guides/function-calling).",
        )

    class ResponseModel(BaseModel):
        final_prompt: str | list[ConversationEntry]

        output_text: list[str]

        # tts
        output_audio: list[str]

        # lipsync
        output_video: list[str]

        # intermediate text
        raw_input_text: str | None
        raw_tts_text: list[str] | None
        raw_output_text: list[str] | None

        # doc search
        references: list[SearchReference] | None
        final_search_query: str | None
        final_keyword_query: str | list[str] | None

        # function calls
        output_documents: list[str] | None
        reply_buttons: list[ReplyButton] | None

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
        st.write(
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
        st.text_area(
            """
            #### 📝 Instructions
            """,
            key="bot_script",
            height=300,
        )
        prompt_vars_widget(
            "bot_script",
        )

        enum_selector(
            LargeLanguageModels,
            label="#### 🧠 Language Model",
            key="selected_model",
            use_selectbox=True,
        )

        document_uploader(
            """
            #### 📄 Knowledge
            Add documents or links to give your copilot a knowledge base. When asked a question, we'll search them to generate an answer with citations. 
            """,
        )

        st.markdown("#### Capabilities")
        if st.checkbox(
            "##### 🗣️ Text to Speech & Lipsync",
            value=bool(st.session_state.get("tts_provider")),
        ):
            text_to_speech_provider_selector(self)
            st.write("---")
            enable_video = st.checkbox(
                "##### 🫦 Add Lipsync Video",
                value=bool(st.session_state.get("input_face")),
            )
        else:
            st.session_state["tts_provider"] = None
            enable_video = False
        if enable_video:
            st.file_uploader(
                """
                ###### 👩‍🦰 Input Face
                Upload a video or image (with a human face) to lipsync responses. mp4, mov, png, jpg or gif preferred.
                """,
                key="input_face",
            )
            st.write("---")
        else:
            st.session_state["input_face"] = None

        if st.checkbox(
            "##### 🔠 Translation",
            value=bool(st.session_state.get("user_language")),
        ):
            google_translate_language_selector(
                f"{field_desc(self.RequestModel, 'user_language')}",
                key="user_language",
            )
            st.write("---")
        else:
            st.session_state["user_language"] = None

        if st.checkbox(
            "##### 🩻 Photo & Document Intelligence",
            value=bool(
                st.session_state.get("document_model"),
            ),
        ):
            doc_model_descriptions = azure_form_recognizer_models()
            st.selectbox(
                f"{field_desc(self.RequestModel, 'document_model')}",
                key="document_model",
                options=[None, *doc_model_descriptions],
                format_func=lambda x: (
                    f"{doc_model_descriptions[x]} ({x})" if x else "———"
                ),
            )

    def validate_form_v2(self):
        input_glossary = st.session_state.get("input_glossary_document", "")
        output_glossary = st.session_state.get("output_glossary_document", "")
        if input_glossary:
            validate_glossary_document(input_glossary)
        if output_glossary:
            validate_glossary_document(output_glossary)

    def render_usage_guide(self):
        youtube_video("-j2su1r8pEg")

    def render_settings(self):
        tts_provider = st.session_state.get("tts_provider")
        if tts_provider:
            text_to_speech_settings(self, tts_provider)
            st.write("---")

        input_face = st.session_state.get("input_face")
        if input_face:
            lipsync_settings()
            st.write("---")

        if st.session_state.get("user_language"):
            st.markdown("##### 🔠 Translation Settings")
            enable_glossary = st.checkbox(
                "📖 Add Glossary",
                value=bool(
                    st.session_state.get("input_glossary_document")
                    or st.session_state.get("output_glossary_document")
                ),
            )
            if enable_glossary:
                st.caption(
                    """
                    Provide a glossary to customize translation and improve accuracy of domain-specific terms.
                    If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing).
                    """
                )
                glossary_input(
                    f"##### {field_title_desc(self.RequestModel, 'input_glossary_document')}",
                    key="input_glossary_document",
                )
                glossary_input(
                    f"##### {field_title_desc(self.RequestModel, 'output_glossary_document')}",
                    key="output_glossary_document",
                )
            else:
                st.session_state["input_glossary_document"] = None
                st.session_state["output_glossary_document"] = None
            st.write("---")

        documents = st.session_state.get("documents")
        if documents:
            st.write("#### 📄 Knowledge Base")
            st.text_area(
                """
            ###### 👩‍🏫 Search Instructions
            How should the LLM interpret the results from your knowledge base?
            """,
                key="task_instructions",
                height=300,
            )
            prompt_vars_widget(
                "task_instructions",
            )

            citation_style_selector()
            st.checkbox("🔗 Shorten Citation URLs", key="use_url_shortener")

            doc_extract_selector()

            st.write("---")

        st.markdown(
            """
            #### Advanced Settings
            In general, you should not need to adjust these.
            """
        )

        if documents:
            query_instructions_widget()
            keyword_instructions_widget()
            doc_search_advanced_settings()
            st.write("---")

        language_model_settings(show_selector=False)

        st.write("---")

        enum_multiselect(
            enum_cls=LLMTools,
            label="##### " + field_title_desc(self.RequestModel, "tools"),
            key="tools",
        )

    def fields_to_save(self) -> [str]:
        fields = super().fields_to_save() + ["landbot_url"]
        if "elevenlabs_api_key" in fields:
            fields.remove("elevenlabs_api_key")
        return fields

    def render_example(self, state: dict):
        input_prompt = state.get("input_prompt")
        if input_prompt:
            st.write(
                "**Prompt**\n```properties\n"
                + truncate_text_words(input_prompt, maxlen=200)
                + "\n```"
            )

        st.write("**Response**")

        output_video = state.get("output_video")
        if output_video:
            st.video(output_video[0], autoplay=True)

        output_text = state.get("output_text")
        if output_text:
            st.write(output_text[0], line_clamp=5)

    def render_output(self):
        # chat window
        with st.div(className="pb-3"):
            chat_list_view()
            (
                pressed_send,
                new_input,
                new_input_images,
                new_input_documents,
            ) = chat_input_view()

        if pressed_send:
            self.on_send(new_input, new_input_images, new_input_documents)

        # clear chat inputs
        if st.button("🗑️ Clear"):
            st.session_state["messages"] = []
            st.session_state["input_prompt"] = ""
            st.session_state["input_images"] = None
            st.session_state["new_input_documents"] = None
            st.session_state["raw_input_text"] = ""
            self.clear_outputs()
            st.session_state["final_keyword_query"] = ""
            st.session_state["final_search_query"] = ""
            st.experimental_rerun()

        # render sources
        references = st.session_state.get("references", [])
        if not references:
            return
        with st.expander("💁‍♀️ Sources"):
            for idx, ref in enumerate(references):
                st.write(f"**{idx + 1}**. [{ref['title']}]({ref['url']})")
                text_output(
                    "Source Document",
                    value=ref["snippet"],
                    label_visibility="collapsed",
                )

    def on_send(
        self,
        new_input: str,
        new_input_images: list[str],
        new_input_documents: list[str],
    ):
        prev_input = st.session_state.get("raw_input_text") or ""
        prev_output = (st.session_state.get("raw_output_text") or [""])[0]
        prev_input_images = st.session_state.get("input_images")
        prev_input_documents = st.session_state.get("input_documents")

        if (prev_input or prev_input_images or prev_input_documents) and prev_output:
            # append previous input to the history
            st.session_state["messages"] = st.session_state.get("messages", []) + [
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
            new_input = f"Files: {filenames}\n\n{new_input}"
        st.session_state["input_prompt"] = new_input
        st.session_state["input_images"] = new_input_images or None
        st.session_state["input_documents"] = new_input_documents or None

        self.on_submit()

    def render_steps(self):
        if st.session_state.get("tts_provider"):
            st.video(st.session_state.get("input_face"), caption="Input Face")

        final_search_query = st.session_state.get("final_search_query")
        if final_search_query:
            st.text_area(
                "**Final Search Query**", value=final_search_query, disabled=True
            )

        final_keyword_query = st.session_state.get("final_keyword_query")
        if final_keyword_query:
            if isinstance(final_keyword_query, list):
                st.write("**Final Keyword Query**")
                st.json(final_keyword_query)
            else:
                st.text_area(
                    "**Final Keyword Query**",
                    value=str(final_keyword_query),
                    disabled=True,
                )

        references = st.session_state.get("references", [])
        if references:
            st.write("**References**")
            st.json(references, expanded=False)

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            if isinstance(final_prompt, str):
                text_output("**Final Prompt**", value=final_prompt, height=300)
            else:
                st.write("**Final Prompt**")
                st.json(final_prompt)

        for idx, text in enumerate(st.session_state.get("raw_output_text", [])):
            st.text_area(
                f"**Raw Text Response {idx + 1}**",
                value=text,
                disabled=True,
            )

        col1, col2 = st.columns(2)
        with col1:
            for idx, text in enumerate(st.session_state.get("output_text", [])):
                st.text_area(
                    f"**Final Response {idx + 1}**",
                    value=text,
                    disabled=True,
                )
        with col2:
            for idx, audio_url in enumerate(st.session_state.get("output_audio", [])):
                st.write(f"**Generated Audio {idx + 1}**")
                st.audio(audio_url)

    def get_raw_price(self, state: dict):
        total = self.get_usage_cost() + 3

        if state.get("tts_provider") == TextToSpeechProviders.ELEVEN_LABS.name:
            output_text_list = state.get(
                "raw_tts_text", state.get("raw_output_text", [])
            )
            tts_state = {"text_prompt": "".join(output_text_list)}
            total += TextToSpeechPage().get_raw_price(tts_state)

        if state.get("input_face"):
            total += 1

        return total * state.get("num_outputs", 1)

    def get_usage_cost(self):
        current_run, published_run = self.get_runs_from_query_params(
            *extract_query_params(gooey_get_query_params())
        )  # type: ignore
        run_id = current_run.run_id or published_run.published_run_id
        return math.ceil(
            UsageCost.objects.filter(saved_run__run_id=run_id).aggregate(
                Sum("dollar_amount")
            )["dollar_amount__sum"]
            or 1
        )

    def additional_notes(self, state: dict):
        notes = f" \\\n*Breakdown: {self.get_usage_cost()} ({state['selected_model']}) + 3/run*"
        tts_provider = st.session_state.get("tts_provider")
        match tts_provider:
            case TextToSpeechProviders.ELEVEN_LABS.name:
                notes += f" *+ {TextToSpeechPage().get_cost_note()} (11labs)*"
        if st.session_state.get("input_face"):
            notes += " *+ 1 (lipsync)*"
        return notes

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: VideoBotsPage.RequestModel = self.RequestModel.parse_obj(state)

        if state.get("tts_provider") == TextToSpeechProviders.ELEVEN_LABS.name and not (
            self.is_current_user_paying() or self.is_current_user_admin()
        ):
            raise UserError(
                """
                Please purchase Gooey.AI credits to use ElevenLabs voices <a href="/account">here</a>.
                """
            )

        state.update(
            dict(final_prompt=[], output_text=[], output_audio=[], output_video=[])
        )

        user_input = request.input_prompt.strip()
        if not (user_input or request.input_images or request.input_documents):
            return
        model = LargeLanguageModels[request.selected_model]
        is_chat_model = model.is_chat_model()
        saved_msgs = request.messages.copy()
        bot_script = request.bot_script

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

        # translate input text
        if request.user_language and request.user_language != "en":
            yield f"Translating Input to English..."
            user_input = run_google_translate(
                texts=[user_input],
                source_language=request.user_language,
                target_language="en",
                glossary_url=request.input_glossary_document,
            )[0]

        if ocr_texts:
            yield f"Translating Image Text to English..."
            ocr_texts = run_google_translate(
                texts=ocr_texts,
                source_language="auto",
                target_language="en",
            )
            for text in ocr_texts:
                user_input = f"Exracted Text: {text!r}\n\n{user_input}"

        # parse the bot script
        # system_message, scripted_msgs = parse_script(bot_script)
        system_message = bot_script.strip()
        scripted_msgs = []

        # consturct the system prompt
        if system_message:
            system_message = render_prompt_vars(system_message, state)
            # insert to top
            system_prompt = {"role": CHATML_ROLE_SYSTEM, "content": system_message}
        else:
            system_prompt = None

        # # get user/bot display names
        # try:
        #     bot_display_name = scripted_msgs[-1]["display_name"]
        # except IndexError:
        #     bot_display_name = CHATML_ROLE_ASSISTANT
        # try:
        #     user_display_name = scripted_msgs[-2]["display_name"]
        # except IndexError:
        #     user_display_name = CHATML_ROLE_USER

        # save raw input for reference
        state["raw_input_text"] = user_input

        # if documents are provided, run doc search on the saved msgs and get back the references
        references = None
        if request.documents:
            # formulate the search query as a history of all the messages
            query_msgs = saved_msgs + [
                format_chat_entry(role=CHATML_ROLE_USER, content=user_input)
            ]
            clip_idx = convo_window_clipper(
                query_msgs, model_max_tokens[model] // 2, sep=" "
            )
            query_msgs = query_msgs[clip_idx:]

            chat_history = "\n".join(
                f'{entry["role"]}: """{get_entry_text(entry)}"""'
                for entry in query_msgs
            )

            query_instructions = (request.query_instructions or "").strip()
            if query_instructions:
                yield "Creating search query..."
                state["final_search_query"] = generate_final_search_query(
                    request=request,
                    instructions=query_instructions,
                    context={**state, "messages": chat_history},
                )
            else:
                query_msgs.reverse()
                state["final_search_query"] = "\n---\n".join(
                    get_entry_text(entry) for entry in query_msgs
                )

            keyword_instructions = (request.keyword_instructions or "").strip()
            if keyword_instructions:
                yield "Finding keywords..."
                k_request = request.copy()
                # other models dont support JSON mode
                k_request.selected_model = LargeLanguageModels.gpt_4_turbo.name
                keyword_query = generate_final_search_query(
                    request=k_request,
                    instructions=keyword_instructions,
                    context={**state, "messages": chat_history},
                    response_format_type="json_object",
                )
                if keyword_query and isinstance(keyword_query, dict):
                    keyword_query = list(keyword_query.values())[0]
                state["final_keyword_query"] = keyword_query
            # return

            # perform doc search
            references = yield from get_top_k_references(
                DocSearchRequest.parse_obj(
                    {
                        **state,
                        "search_query": state["final_search_query"],
                        "keyword_query": state.get("final_keyword_query"),
                    },
                ),
            )
            if request.use_url_shortener:
                for reference in references:
                    reference["url"] = ShortenedURL.objects.get_or_create_for_workflow(
                        url=reference["url"],
                        user=self.request.user,
                        workflow=Workflow.VIDEO_BOTS,
                    )[0].shortened_url()
            state["references"] = references
        # if doc search is successful, add the search results to the user prompt
        if references:
            # add task instructions
            task_instructions = render_prompt_vars(request.task_instructions, state)
            user_input = (
                references_as_prompt(references)
                + f"\n**********\n{task_instructions.strip()}\n**********\n"
                + user_input
            )

        # construct user prompt
        user_prompt = format_chat_entry(
            role=CHATML_ROLE_USER, content=user_input, images=request.input_images
        )

        # truncate the history to fit the model's max tokens
        history_window = scripted_msgs + saved_msgs
        max_history_tokens = (
            model_max_tokens[model]
            - calc_gpt_tokens([system_prompt, user_input])
            - request.max_tokens
            - SAFETY_BUFFER
        )
        clip_idx = convo_window_clipper(
            history_window,
            max_history_tokens,
        )
        history_window = history_window[clip_idx:]
        prompt_messages = [system_prompt, *history_window, user_prompt]
        state["final_prompt"] = prompt_messages

        # ensure input script is not too big
        max_allowed_tokens = model_max_tokens[model] - calc_gpt_tokens(prompt_messages)
        max_allowed_tokens = min(max_allowed_tokens, request.max_tokens)
        if max_allowed_tokens < 0:
            raise UserError("Input Script is too long! Please reduce the script size.")

        yield f"Summarizing with {model.value}..."
        chunks = run_language_model(
            model=request.selected_model,
            messages=[
                {"role": s["role"], "content": s["content"]} for s in prompt_messages
            ],
            max_tokens=max_allowed_tokens,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
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
                state["output_documents"] = output_documents = []
                for call in entries[0].get("tool_calls") or []:
                    result = yield from exec_tool_call(call)
                    output_documents.append(result)

            # save model response
            state["raw_output_text"] = [
                "".join(snippet for snippet, _ in parse_refs(text, references))
                for text in output_text
            ]

            # translate response text
            if request.user_language and request.user_language != "en":
                yield f"Translating response to {request.user_language}..."
                output_text = run_google_translate(
                    texts=output_text,
                    source_language="en",
                    target_language=request.user_language,
                    glossary_url=request.output_glossary_document,
                )
                state["raw_tts_text"] = [
                    "".join(snippet for snippet, _ in parse_refs(text, references))
                    for text in output_text
                ]

            if references:
                all_refs_list = apply_response_formattings_prefix(
                    output_text, references, citation_style
                )
            else:
                all_refs_list = None

            state["output_text"] = output_text
            if all(entry.get("finish_reason") for entry in entries):
                if all_refs_list:
                    apply_response_formattings_suffix(
                        all_refs_list, state["output_text"], citation_style
                    )
                finish_reason = entries[0]["finish_reason"]
                yield f"Completed with {finish_reason=}"  # avoid changing this message since it's used to detect end of stream
            else:
                yield f"Streaming{str(i + 1).translate(SUPERSCRIPT)} {model.value}..."

        if not request.tts_provider:
            return
        tts_state = dict(state)
        for text in state.get("raw_tts_text", state["raw_output_text"]):
            tts_state["text_prompt"] = text
            yield from TextToSpeechPage(
                request=self.request, run_user=self.run_user
            ).run(tts_state)
            state["output_audio"].append(tts_state["audio_url"])

        if not request.input_face:
            return
        lip_state = dict(state)
        for audio_url in state["output_audio"]:
            lip_state["input_audio"] = audio_url
            yield from LipsyncPage(request=self.request, run_user=self.run_user).run(
                lip_state
            )
            state["output_video"].append(lip_state["output_video"])

    def get_tabs(self):
        tabs = super().get_tabs()
        tabs.extend([MenuTabs.integrations])
        return tabs

    def render_selected_tab(self, selected_tab):
        super().render_selected_tab(selected_tab)

        if selected_tab == MenuTabs.integrations:
            st.newline()

            # not signed in case
            if not self.request.user or self.request.user.is_anonymous:
                self.integration_welcome_screen()
                st.newline()
                with st.center():
                    st.anchor(
                        "Get Started",
                        href=self.get_auth_url(self.app_url(query_params={})),
                        type="primary",
                    )
                return

            current_run, published_run = self.get_runs_from_query_params(
                *extract_query_params(gooey_get_query_params())
            )  # type: ignore

            # signed in but not on a run the user can edit (admins will never see this)
            if not self.can_user_edit_run(current_run, published_run):
                self.integration_welcome_screen(
                    title="Create your Saved Copilot",
                )
                st.newline()
                with st.center():
                    st.anchor(
                        "Run & Save this Copilot",
                        href=self.get_auth_url(self.app_url(query_params={})),
                        type="primary",
                    )
                return

            # signed, has submitted run, but not published (admins will never see this)
            # note: this means we no longer allow botintegrations on non-published runs which is a breaking change requested by Sean
            if not self.can_user_edit_published_run(published_run):
                self.integration_welcome_screen(
                    title="Save your Published Copilot",
                )
                st.newline()
                with st.center():
                    self._render_published_run_buttons(
                        current_run=current_run,
                        published_run=published_run,
                        redirect_to=self.get_tab_url(MenuTabs.integrations),
                    )
                return

            # if we come from an integration redirect, we connect the integrations
            if "connect_ids" in self.request.query_params:
                self.integrations_on_connect(
                    current_run,
                    published_run,
                )

            # see which integrations are available to the user for the current published run
            assert published_run, "At this point, published_run should be available"
            integrations_q = Q(published_run=published_run) | Q(
                saved_run__example_id=published_run.published_run_id
            )
            if not self.is_current_user_admin():
                integrations_q &= Q(billing_account_uid=self.request.user.uid)

            integrations: QuerySet[BotIntegration] = BotIntegration.objects.filter(
                integrations_q
            ).order_by("platform", "-created_at")

            # signed in, can edit, but no connected botintegrations on this run
            if not integrations.exists():
                self.integration_connect_screen()
                return

            # signed in, can edit, and has connected botintegrations on this run
            with st.center():
                self.integration_test_config_screen(
                    integrations, current_run, published_run
                )

    def integrations_on_connect(self, current_run, published_run):
        from app_users.models import AppUser
        from daras_ai_v2.base import RedirectException
        from daras_ai_v2.slack_bot import send_confirmation_msg

        for bid in self.request.query_params.getlist("connect_ids"):
            bi = BotIntegration.objects.filter(id=bid).first()
            if not bi:
                continue
            if bi.saved_run is not None:
                with st.center():
                    st.write(
                        f"⚠️ {bi.get_display_name()} is already connected to a different published run by {AppUser.objects.filter(uid=bi.billing_account_uid).first().display_name}. Please disconnect it first."
                    )
                return

            bi.streaming_enabled = True
            bi.user_language = st.session_state.get("user_language") or bi.user_language
            bi.saved_run = current_run
            if published_run and published_run.saved_run_id == current_run.id:
                bi.published_run = published_run
            else:
                bi.published_run = None
            if bi.platform == Platform.SLACK:
                bi.slack_create_personal_channels = False
                send_confirmation_msg(bi)
            bi.save()

        raise RedirectException(self.get_tab_url(MenuTabs.integrations))

    def integration_welcome_screen(self, title="Connect your Copilot"):
        with st.center():
            st.markdown(f"#### {title}")

        col1, col2, col3 = st.columns(
            3,
            column_props=dict(
                style={
                    "display": "flex",
                    "flex-direction": "column",
                    "align-items": "center",
                    "text-align": "center",
                    "max-width": "300px",
                }
            ),
            style={"justify-content": "center"},
        )
        with col1:
            st.html("🏃‍♀️", style={"fontSize": "4rem"})
            st.markdown(
                """
                1. Fork & Save your Run
                """
            )
            st.caption("Make changes, Submit & Save your perfect workflow")
        with col2:
            st.image(INTEGRATION_IMG, alt="Integrations", style={"height": "5rem"})
            st.markdown("2. Connect to Slack, Whatsapp or your App")
            st.caption("Or Facebook, Instagram and the web. Wherever your users chat.")
        with col3:
            st.html("📈", style={"fontSize": "4rem"})
            st.markdown("3. Test, Analyze & Iterate")
            st.caption("Analyze your usage. Update your Saved Run to test changes.")

    def integration_connect_screen(
        self, title="Connect your Copilot", status: str | None = None
    ):
        from routers.facebook_api import ig_connect_url, fb_connect_url, wa_connect_url
        from routers.slack_api import slack_connect_url

        on_connect = self.get_tab_url(MenuTabs.integrations)

        with st.center():
            st.markdown(
                f"""
                #### {title}
                {status or f'Run Saved ✅ • <b>Connect</b> • <span style="color: {GRAYCOLOR}">Test & Configure</span>'}
                """,
                unsafe_allow_html=True,
            )

            LINKSTYLE = 'class="btn btn-theme btn-secondary" style="margin: 0; display: flex; justify-content: center; align-items: center; padding: 8px; border: 1px solid black; min-width: 120px; width: 160px; aspect-ratio: 5 / 2; overflow: hidden; border-radius: 10px" draggable="false"'
            IMGSTYLE = 'style="width: 80%" draggable="false"'
            ROWSTYLE = 'style="display: flex; align-items: center; gap: 1em; margin-bottom: 1rem" draggable="false"'
            DESCRIPTIONSTYLE = f'style="color: {GRAYCOLOR}; text-align: left"'
            st.markdown(
                # language=html
                f"""
                <div>
                <div {ROWSTYLE}>
                    <a href="{wa_connect_url(on_connect)}" {LINKSTYLE} aria-label="Connect your Whatsapp number">
                        <img src="{WHATSAPP_IMG}" {IMGSTYLE} alt="Whatsapp">
                    </a>
                    <div {DESCRIPTIONSTYLE}>Bring your own <a href="https://business.facebook.com/wa/manage/phone-numbers">WhatsApp number</a> to connect. Need a new one? Email <a href="mailto:sales@gooey.ai">sales@gooey.ai</a>.</div>
                </div>
                <div {ROWSTYLE}>
                    <a href="{slack_connect_url(on_connect)}" {LINKSTYLE} aria-label="Connect your Slack Workspace">
                        <img src="{SLACK_IMG}" {IMGSTYLE} alt="Slack">
                    </a>
                    <div {DESCRIPTIONSTYLE}>Connect to a Slack Channel. <a href="https://gooey.ai/docs/guides/copilot/deploy-to-slack">Help Guide</a>.</div>
                </div>
                <div {ROWSTYLE}>
                    <a href="{fb_connect_url(on_connect)}" {LINKSTYLE} aria-label="Connect your Facebook Page">
                        <img src="{FACEBOOK_IMG}" {IMGSTYLE} alt="Facebook Messenger">
                    </a>
                    <div {DESCRIPTIONSTYLE}>Connect to a Facebook Page you own. <a href="https://gooey.ai/docs/guides/copilot/deploy-to-facebook">Help Guide</a>.</div>
                </div>
                <!--<div {ROWSTYLE}>
                    <a href="{ig_connect_url(on_connect)}" {LINKSTYLE} aria-label="Connect your Instagram Page">
                        <img src="{INSTAGRAM_IMG}" {IMGSTYLE} alt="Instagram">
                    </a>
                    <div {DESCRIPTIONSTYLE}>Connect to an Instagram account you own.</div>
                </div>-->
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.newline()
            st.write(
                f"Or use [our API]({self.get_tab_url(MenuTabs.run_as_api)}) to integrate with your own app."
            )

    def integration_test_config_screen(
        self, integrations: QuerySet[BotIntegration], current_run, published_run
    ):
        from daras_ai_v2.base import RedirectException, get_title_breadcrumbs
        from recipes.VideoBotsStats import VideoBotsStatsPage

        # from recipes.BulkRunner import BulkRunnerPage
        from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button

        run_title = get_title_breadcrumbs(
            VideoBotsPage, current_run, published_run
        ).h1_title

        add_integration = self.get_tab_url(
            MenuTabs.integrations, query_params={"add-integration": "true"}
        )
        if self.request.query_params.get("add-integration") == "true":
            cancel = self.get_tab_url(MenuTabs.integrations)
            self.integration_connect_screen(
                "Configure your Copilot: Add a New Integration",
                f'Run Saved ✅ • <b>Connected</b> ✅ • <a href="{cancel}">Test & Configure</a> ✅',
            )
            if st.button("Return to Test & Configure"):
                raise RedirectException(cancel)
            return

        st.markdown("#### Configure your Copilot")

        if integrations.count() > 1:
            with st.div(style={"minWidth": "500px", "textAlign": "left"}):
                integrations_map = {i.id: i for i in integrations}
                bi_id = st.selectbox(
                    label="",
                    options=integrations_map.keys(),
                    format_func=lambda bi_id: f'<img width="20" height="20" style="margin-right: 10px" src="{Platform(integrations_map[bi_id].platform).get_favicon()}" /> {integrations_map[bi_id].name}',
                    key="bi_id",
                )
                bi = integrations_map[bi_id]
        else:
            bi = integrations[0]
        icon = f'<img src="{Platform(bi.platform).get_favicon()}" width="20" height="20" />'

        st.newline()
        with st.div(style={"width": "100%", "textAlign": "left"}):
            test_link = get_bot_test_link(bi)
            col1, col2 = st.columns(2, style={"align-items": "center"})
            with col1:
                st.write("###### Connected To")
                st.write(f"{icon} {bi}", unsafe_allow_html=True)
            with col2:
                if test_link:
                    copy_to_clipboard_button(
                        f'<i class="fa-regular fa-link"></i> Copy {Platform(bi.platform).label} Link',
                        value=test_link,
                        type="secondary",
                    )
                else:
                    st.write("Message quicklink not available.")

            col1, col2 = st.columns(2, style={"align-items": "center"})
            with col1:
                st.write("###### Test")
                st.caption(f"Send a test {Platform(bi.platform).label} message.")
            with col2:
                if test_link:
                    st.anchor(
                        f"{icon} Message {bi.get_display_name()}",
                        test_link,
                        unsafe_allow_html=True,
                    )
                else:
                    st.write("Message quicklink not available.")

            col1, col2 = st.columns(2, style={"align-items": "center"})
            with col1:
                st.write("###### Understand your Users")
                st.caption(f"See real-time analytics.")
            with col2:
                stats_url = furl(
                    VideoBotsStatsPage.app_url(), args={"bi_id": bi.id}
                ).tostr()
                st.anchor(
                    "📊 View Analytics",
                    stats_url,
                )

            # ==== future changes ====
            # col1, col2 = st.columns(2, style={"align-items": "center"})
            # with col1:
            #     st.write("###### Evaluate ⚖️")
            #     st.caption(f"Run automated tests against sample user messages.")
            # with col2:
            #     st.anchor(
            #         "Run Bulk Tests",
            #         BulkRunnerPage.app_url(),
            #     )

            # st.write("#### Automated Analysis 🧠")
            # st.caption(
            #     "Add a Gooey.AI LLM prompt to automatically analyse and categorize user messages. [Example](https://gooey.ai/compare-large-language-models/how-farmerchat-turns-conversations-to-structured-data/?example_id=lbjnoem7) and [Guide](https://gooey.ai/docs/guides/copilot/conversation-analysis)."
            # )

            if bi.platform == Platform.WHATSAPP and bi.wa_business_waba_id:
                col1, col2 = st.columns(2, style={"align-items": "center"})
                with col1:
                    st.write("###### WhatsApp Business Management")
                    st.caption(
                        f"Access your WhatsApp account on Meta to approve message templates, etc."
                    )
                with col2:
                    st.anchor(
                        "Business Settings",
                        f"https://business.facebook.com/settings/whatsapp-business-accounts/{bi.wa_business_waba_id}",
                        new_tab=True,
                    )
                    st.anchor(
                        "WhatsApp Manager",
                        f"https://business.facebook.com/wa/manage/home/?waba_id={bi.wa_business_waba_id}",
                        new_tab=True,
                    )

            col1, col2 = st.columns(2, style={"align-items": "center"})
            with col1:
                st.write("###### Add Integration")
                st.caption(f"Add another connection for {run_title}.")
            with col2:
                if st.button(
                    f'<img align="left" width="24" height="24" src="{INTEGRATION_IMG}"> &nbsp; Add Integration',
                    key="btn_connect",
                ):
                    raise RedirectException(add_integration)

            with st.expander("Configure Settings 🛠️"):
                if bi.platform == Platform.SLACK:
                    slack_specific_settings(bi, run_title)
                general_integration_settings(bi)

                if bi.platform in [Platform.SLACK, Platform.WHATSAPP]:
                    st.newline()
                    st.newline()
                    broadcast_input(bi)

                st.write("---")
                col1, col2 = st.columns(2, style={"align-items": "center"})
                with col1:
                    st.write("###### Disconnect")
                    st.caption(
                        f"Disconnect {run_title} from {Platform(bi.platform).label} {bi.get_display_name()}."
                    )
                with col2:
                    if st.button(
                        "💔️ Disconnect",
                        key="btn_disconnect",
                    ):
                        bi.saved_run = None
                        bi.published_run = None
                        bi.save()
                        st.experimental_rerun()


def chat_list_view():
    # render a reversed list view
    with st.div(
        className="pb-1",
        style=dict(
            maxHeight="80vh",
            overflowY="scroll",
            display="flex",
            flexDirection="column-reverse",
            border="1px solid #c9c9c9",
        ),
    ):
        with st.div(className="px-3"):
            show_raw_msgs = st.checkbox("_Show Raw Output_")
        # render the last output
        with msg_container_widget(CHATML_ROLE_ASSISTANT):
            if show_raw_msgs:
                output_text = st.session_state.get("raw_output_text", [])
            else:
                output_text = st.session_state.get("output_text", [])
            output_video = st.session_state.get("output_video", [])
            output_audio = st.session_state.get("output_audio", [])
            if output_text:
                st.write(f"**Assistant**")
                for idx, text in enumerate(output_text):
                    st.write(text)
                    try:
                        st.video(output_video[idx], autoplay=True)
                    except IndexError:
                        try:
                            st.audio(output_audio[idx])
                        except IndexError:
                            pass
            output_documents = st.session_state.get("output_documents", [])
            if output_documents:
                for doc in output_documents:
                    st.write(doc)
        messages = st.session_state.get("messages", []).copy()
        # add last input to history if present
        if show_raw_msgs:
            input_prompt = st.session_state.get("raw_input_text")
        else:
            input_prompt = st.session_state.get("input_prompt")
        input_images = st.session_state.get("input_images")
        if input_prompt or input_images:
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
                if text or images:
                    st.write(f"**{entry['role'].capitalize()}**  \n{text}")
                if images:
                    for im in images:
                        st.image(im, style={"maxHeight": "200px"})


def chat_input_view() -> tuple[bool, str, list[str], list[str]]:
    with st.div(
        className="px-3 pt-3 d-flex gap-1",
        style=dict(background="rgba(239, 239, 239, 0.6)"),
    ):
        show_uploader_key = "--show-file-uploader"
        show_uploader = st.session_state.setdefault(show_uploader_key, False)
        if st.button(
            "📎",
            style=dict(height="3.2rem", backgroundColor="white"),
        ):
            show_uploader = not show_uploader
            st.session_state[show_uploader_key] = show_uploader

        with st.div(className="flex-grow-1"):
            new_input = st.text_area("", placeholder="Send a message", height=50)

        pressed_send = st.button("✈ Send", style=dict(height="3.2rem"))

    if show_uploader:
        uploaded_files = st.file_uploader("", accept_multiple_files=True)
        new_input_images = []
        new_input_documents = []
        for f in uploaded_files:
            mime_type = mimetypes.guess_type(f)[0] or ""
            if mime_type.startswith("image/"):
                new_input_images.append(f)
            else:
                new_input_documents.append(f)
    else:
        new_input_images = None
        new_input_documents = None

    return pressed_send, new_input, new_input_images, new_input_documents


def msg_container_widget(role: str):
    return st.div(
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
    sep: str = "",
    is_chat_model: bool = True,
    step=2,
):
    for i in range(len(window) - 2, -1, -step):
        if calc_gpt_tokens(window[i:], sep=sep) > max_tokens:
            return i + step
    return 0
