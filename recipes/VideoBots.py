import json
import mimetypes
import os
import os.path
import typing

from django.db.models import QuerySet, Q
from furl import furl
from pydantic import BaseModel, Field

import gooey_ui as st
from bots.models import BotIntegration, Platform
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
)
from daras_ai_v2.base import BasePage, MenuTabs
from daras_ai_v2.bot_integration_widgets import (
    general_integration_settings,
    broadcast_input,
    render_bot_test_link,
)
from daras_ai_v2.doc_search_settings_widgets import (
    doc_search_settings,
    document_uploader,
)
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.functions import LLMTools
from daras_ai_v2.glossary import glossary_input, validate_glossary_document
from daras_ai_v2.language_model import (
    run_language_model,
    calc_gpt_tokens,
    ConversationEntry,
    format_chatml_message,
    CHATML_END_TOKEN,
    CHATML_START_TOKEN,
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

# BOT_SCRIPT_RE = re.compile(
#     # start of line
#     r"^"
#     # name of bot / user
#     r"([\w\ \t]{3,30})"
#     # colon
#     r"\:\ ",
#     flags=re.M,
# )

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
        dense_weight: float | None = DocSearchRequest.__fields__[
            "dense_weight"
        ].field_info

        citation_style: typing.Literal[tuple(e.name for e in CitationStyles)] | None
        use_url_shortener: bool | None

        user_language: str | None = Field(
            title="🔠 User Language",
            description="If provided, the copilot will translate user messages to English and the copilot's response back to the selected language.",
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
            #### 📝 Prompt
            High-level system instructions.
            """,
            key="bot_script",
            height=300,
        )

        document_uploader(
            """
#### 📄 Documents (*optional*)
Upload documents or enter URLs to give your copilot a knowledge base. With each incoming user message, we'll search your documents via a vector DB query.
"""
        )

        prompt_vars_widget(
            "bot_script",
            "task_instructions",
            "query_instructions",
            "keyword_instructions",
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
        if st.session_state.get("documents") or st.session_state.get(
            "__documents_files"
        ):
            st.text_area(
                """
            ##### 👩‍🏫 Document Search Results Instructions
            Guidelines to interpret the results of the knowledge base query.
            """,
                key="task_instructions",
                height=300,
            )

            st.write("---")
            st.checkbox("🔗 Shorten Citation URLs", key="use_url_shortener")
            st.caption(
                "Shorten citation links and enable click tracking of knowledge base URLs, docs, PDF and/or videos."
            )
            st.write("---")
            doc_search_settings(keyword_instructions_allowed=True)
            st.write("---")

        language_model_settings(show_document_model=True)

        st.write("---")
        google_translate_language_selector(
            f"##### {field_title_desc(self.RequestModel, 'user_language')}",
            key="user_language",
        )
        enable_glossary = st.checkbox(
            "📖 Customize with Glossary",
            value=bool(
                st.session_state.get("input_glossary_document")
                or st.session_state.get("output_glossary_document")
            ),
        )
        st.markdown(
            """
            Provide a glossary to customize translation and improve accuracy of domain-specific terms.
            If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing).
            """
        )
        if enable_glossary:
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

        if not "__enable_audio" in st.session_state:
            st.session_state["__enable_audio"] = bool(
                st.session_state.get("tts_provider")
            )
        enable_audio = st.checkbox("Enable Audio Output?", key="__enable_audio")
        if not enable_audio:
            st.write("---")
            st.session_state["tts_provider"] = None
        else:
            text_to_speech_settings(page=self)

        st.write("---")
        if not "__enable_video" in st.session_state:
            st.session_state["__enable_video"] = bool(
                st.session_state.get("input_face")
            )
        enable_video = st.checkbox("Enable Video Output?", key="__enable_video")
        if not enable_video:
            st.session_state["input_face"] = None
        else:
            st.file_uploader(
                """
                #### 👩‍🦰 Input Face
                Upload a video/image that contains faces to use
                *Recommended - mp4 / mov / png / jpg / gif*
                """,
                key="input_face",
            )
            lipsync_settings()

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
            st.write(truncate_text_words(output_text[0], maxlen=200))

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
        match state.get("tts_provider"):
            case TextToSpeechProviders.ELEVEN_LABS.name:
                output_text_list = state.get(
                    "raw_tts_text", state.get("raw_output_text", [])
                )
                tts_state = {"text_prompt": "".join(output_text_list)}
                return super().get_raw_price(state) + TextToSpeechPage().get_raw_price(
                    tts_state
                )
            case _:
                return super().get_raw_price(state)

    def additional_notes(self):
        tts_provider = st.session_state.get("tts_provider")
        match tts_provider:
            case TextToSpeechProviders.ELEVEN_LABS.name:
                return f"""
                    - *Base cost = {super().get_raw_price(st.session_state)} credits*
                    - *Additional {TextToSpeechPage().additional_notes()}*
                """
            case _:
                return ""

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: VideoBotsPage.RequestModel = self.RequestModel.parse_obj(state)

        if state.get("tts_provider") == TextToSpeechProviders.ELEVEN_LABS.name:
            assert (
                self.is_current_user_paying() or self.is_current_user_admin()
            ), """
                Please purchase Gooey.AI credits to use ElevenLabs voices <a href="/account">here</a>.
                """

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
            - calc_gpt_tokens([system_prompt, user_input], is_chat_model=is_chat_model)
            - request.max_tokens
            - SAFETY_BUFFER
        )
        clip_idx = convo_window_clipper(
            history_window, max_history_tokens, is_chat_model=is_chat_model
        )
        history_window = history_window[clip_idx:]
        prompt_messages = [system_prompt, *history_window, user_prompt]

        # for backwards compat with non-chat models
        if not is_chat_model:
            # assistant prompt to triger a model response
            prompt_messages.append(
                {
                    "role": CHATML_ROLE_ASSISTANT,
                    "content": "",
                }
            )

        state["final_prompt"] = prompt_messages

        # ensure input script is not too big
        max_allowed_tokens = model_max_tokens[model] - calc_gpt_tokens(
            prompt_messages, is_chat_model=is_chat_model
        )
        max_allowed_tokens = min(max_allowed_tokens, request.max_tokens)
        if max_allowed_tokens < 0:
            raise ValueError("Input Script is too long! Please reduce the script size.")

        yield f"Summarizing with {model.value}..."
        if is_chat_model:
            chunks = run_language_model(
                model=request.selected_model,
                messages=[
                    {"role": s["role"], "content": s["content"]}
                    for s in prompt_messages
                ],
                max_tokens=max_allowed_tokens,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                avoid_repetition=request.avoid_repetition,
                tools=request.tools,
                stream=True,
            )
        else:
            prompt = "\n".join(
                format_chatml_message(entry) for entry in prompt_messages
            )
            chunks = run_language_model(
                model=request.selected_model,
                prompt=prompt,
                max_tokens=max_allowed_tokens,
                quality=request.quality,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                avoid_repetition=request.avoid_repetition,
                stop=[CHATML_END_TOKEN, CHATML_START_TOKEN],
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

        state["output_audio"] = []
        state["output_video"] = []

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
            if not self.request.user or self.request.user.is_anonymous:
                st.write(
                    "**Please Login to connect this workflow to Your Website, Instagram, Whatsapp & More**"
                )
                return

            self.messenger_bot_integration()

            st.markdown(
                """
                ### How to Integrate Chatbots
                """
            )

            col1, col2 = st.columns(2)
            with col1:
                st.write(
                    """
                    #### Part 1:
                    [Interactive Chatbots for your Content - Part 1: Make your Chatbot - How to use Gooey.AI Workflows ](https://youtu.be/-j2su1r8pEg)
                    """
                )
                st.markdown(
                    """
                    <div style="position: relative; padding-bottom: 56.25%; height: 0; width:100%">
                            <iframe src="https://www.youtube.com/embed/-j2su1r8pEg" title="YouTube video player" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">
                    </iframe>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col2:
                st.write(
                    """

                    #### Part 2:
                    [Interactive Chatbots for your Content - Part 2: Make your Chatbot - How to use Gooey.AI Workflows ](https://youtu.be/h817RolPjq4)
                    """
                )
                st.markdown(
                    """
                    <div style="position: relative; padding-bottom: 56.25%; height: 0;">
                            <iframe src="https://www.youtube.com/embed/h817RolPjq4" title="YouTube video player" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">
                    </iframe>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # st.write("---")
            # st.text_input(
            #     "###### 🤖 [Landbot](https://landbot.io/) URL", key="landbot_url"
            # )
            # show_landbot_widget()

    def messenger_bot_integration(self):
        from routers.facebook_api import ig_connect_url, fb_connect_url
        from routers.slack_api import slack_connect_url
        from recipes.VideoBotsStats import VideoBotsStatsPage

        st.markdown(
            # language=html
            f"""
            <h3>Connect this bot to your Website, Instagram, Whatsapp & More</h3>

            Your can connect your FB Messenger account and Slack Workspace here directly.<br>
            If you ping us at support@gooey.ai, we'll add your other accounts too!

            <!--
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{ig_connect_url}">
                <img height="20" src="https://www.instagram.com/favicon.ico">️
                &nbsp;
                Add Your Instagram Page
                </a>
            </div>
            -->
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{fb_connect_url}">
                <img height="20" src="https://www.facebook.com/favicon.ico">️
                &nbsp;
                Add Your Facebook Page
                </a>
            </div>
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{slack_connect_url}">
                <img height="20" src="https://www.slack.com/favicon.ico">
                &nbsp;
                Add Your Slack Workspace
                </a>
                <a target="_blank" href="https://gooey.ai/docs/guides/copilot/deploy-to-slack" class="streamlit-like-btn" aria-label="docs">
                <img height="20" width="0" src="https://www.slack.com/favicon.ico">   <!-- for vertical alignment -->
                ℹ️
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("---")

        st.button("🔄 Refresh")

        current_run, published_run = self.get_runs_from_query_params(
            *extract_query_params(gooey_get_query_params())
        )  # type: ignore

        integrations_q = Q(billing_account_uid=self.request.user.uid)

        # show admins all the bots connected to the current run
        if self.is_current_user_admin():
            integrations_q |= Q(saved_run=current_run)
            if published_run:
                integrations_q |= Q(
                    saved_run__example_id=published_run.published_run_id
                )
                integrations_q |= Q(published_run=published_run)

        integrations: QuerySet[BotIntegration] = BotIntegration.objects.filter(
            integrations_q
        ).order_by("platform", "-created_at")

        if not integrations:
            return

        for bi in integrations:
            is_connected = (bi.saved_run == current_run) or (
                (
                    bi.saved_run
                    and published_run
                    and bi.saved_run.example_id == published_run.published_run_id
                )
                or (
                    bi.published_run
                    and published_run
                    and bi.published_run == published_run
                )
            )
            col1, col2, col3, *_ = st.columns([1, 1, 2])
            with col1:
                favicon = Platform(bi.platform).get_favicon()
                if bi.published_run:
                    url = self.app_url(
                        example_id=bi.published_run.published_run_id,
                        tab_name=MenuTabs.paths[MenuTabs.integrations],
                    )
                elif bi.saved_run:
                    url = self.app_url(
                        run_id=bi.saved_run.run_id,
                        uid=bi.saved_run.uid,
                        example_id=bi.saved_run.example_id,
                        tab_name=MenuTabs.paths[MenuTabs.integrations],
                    )
                else:
                    url = None
                if url:
                    href = f'<a href="{url}">{bi}</a>'
                else:
                    href = f"<span>{bi}</span>"
                with st.div(className="mt-2"):
                    st.markdown(
                        f'<img height="20" width="20" src={favicon!r}>&nbsp;&nbsp;{href}',
                        unsafe_allow_html=True,
                    )
            with col2:
                pressed_connect = st.button(
                    "🔌💔️ Disconnect" if is_connected else "🖇️ Connect",
                    key=f"btn_connect_{bi.id}",
                    type="tertiary",
                )
                render_bot_test_link(bi)
                stats_url = furl(VideoBotsStatsPage.app_url(), args={"bi_id": bi.id})
                st.html(
                    f"""
                    <a class="btn btn-theme btn-tertiary d-inline-block" target="blank" href="{stats_url}">📊 Analytics</a>
                    """
                )
            if is_connected:
                with col3, st.expander(f"📨 {bi.get_platform_display()} Settings"):
                    if bi.platform == Platform.SLACK:
                        self.slack_specific_settings(bi)
                    general_integration_settings(bi)
                    if bi.platform in [Platform.SLACK, Platform.WHATSAPP]:
                        st.write("---")
                        broadcast_input(bi)
            if not pressed_connect:
                continue
            if is_connected:
                bi.saved_run = None
                bi.published_run = None
            else:
                # set bot language from state
                bi.user_language = (
                    st.session_state.get("user_language") or bi.user_language
                )
                bi.saved_run = current_run
                if published_run and published_run.saved_run_id == current_run.id:
                    bi.published_run = published_run
                else:
                    bi.published_run = None
                if bi.platform == Platform.SLACK:
                    from daras_ai_v2.slack_bot import send_confirmation_msg

                    send_confirmation_msg(bi)
            bi.save()
            st.experimental_rerun()

        st.write("---")

    def slack_specific_settings(self, bi: BotIntegration):
        if st.session_state.get(f"_bi_reset_{bi.id}"):
            pr = self.get_current_published_run()
            st.session_state[f"_bi_name_{bi.id}"] = (
                pr and pr.title
            ) or self.get_recipe_title()
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


def show_landbot_widget():
    landbot_url = st.session_state.get("landbot_url")
    if not landbot_url:
        st.html("", **{"data-landbot-config-url": ""})
        return

    f = furl(landbot_url)
    config_path = os.path.join(f.host, *f.path.segments[:2])
    config_url = f"https://storage.googleapis.com/{config_path}/index.json"

    st.html(
        # language=HTML
        """
<script>
function updateLandbotWidget() {
    if (window.myLandbot) {
        try {
            window.myLandbot.destroy();
        } catch (e) {}
    }
    const configUrl = document.querySelector("[data-landbot-config-url]")?.getAttribute("data-landbot-config-url");
    if (configUrl) {
        window.myLandbot = new Landbot.Livechat({ configUrl });
    }
}
if (typeof Landbot === "undefined") {
    const script = document.createElement("script");
    script.src = "https://cdn.landbot.io/landbot-3/landbot-3.0.0.js";
    script.async = true;
    script.defer = true;
    script.onload = () => {
        window.waitUntilHydrated.then(updateLandbotWidget);
        window.addEventListener("hydrated", updateLandbotWidget);
    };
    document.body.appendChild(script);
}
</script>
        """,
        **{"data-landbot-config-url": config_url},
    )


# def parse_script(bot_script: str) -> (str, list[ConversationEntry]):
#     # run regex to find scripted messages in script text
#     script_matches = list(BOT_SCRIPT_RE.finditer(bot_script))
#     # extract system message from script
#     system_message = bot_script
#     if script_matches:
#         system_message = system_message[: script_matches[0].start()]
#     system_message = system_message.strip()
#     # extract pre-scripted messages from script
#     scripted_msgs: list[ConversationEntry] = []
#     for idx in range(len(script_matches)):
#         match = script_matches[idx]
#         try:
#             next_match = script_matches[idx + 1]
#         except IndexError:
#             next_match_start = None
#         else:
#             next_match_start = next_match.start()
#         if (len(script_matches) - idx) % 2 == 0:
#             role = CHATML_ROLE_USER
#         else:
#             role = CHATML_ROLE_ASSISTANT
#         scripted_msgs.append(
#             {
#                 "role": role,
#                 "display_name": match.group(1).strip(),
#                 "content": bot_script[match.end() : next_match_start].strip(),
#             }
#         )
#     return system_message, scripted_msgs


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
        if (
            calc_gpt_tokens(window[i:], sep=sep, is_chat_model=is_chat_model)
            > max_tokens
        ):
            return i + step
    return 0
