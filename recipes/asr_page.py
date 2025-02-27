import typing

import gooey_gui as gui
from jinja2.lexer import whitespace_re
from pydantic import BaseModel, Field

from bots.models import Workflow, SavedRun, PublishedRun
from daras_ai_v2.asr import (
    language_filter_selector,
    asr_language_selector,
    AsrModels,
    AsrOutputFormat,
    AsrOutputJson,
    forced_asr_languages,
    asr_model_selector,
    run_asr,
    run_translate,
    translation_language_selector,
    translation_model_selector,
    TranslationModels,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    SUPPORTED_SPREADSHEET_TYPES,
)
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc, field_title
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_filters import asr_languages_without_dialects
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.text_output_widget import text_outputs
from recipes.DocSearch import render_documents
from recipes.Translation import TranslationOptions

DEFAULT_ASR_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1916825c-93fa-11ee-97be-02420a0001c8/Speech.jpg.png"


class AsrPage(BasePage):
    title = "Speech Recognition & Translation"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/5fb7e5f6-88d9-11ee-aa86-02420a000165/Speech.png.png"
    workflow = Workflow.ASR
    slug_versions = ["asr", "speech"]

    sane_defaults = dict(output_format=AsrOutputFormat.text.name)

    class RequestModelBase(BasePage.RequestModel):
        documents: list[FieldHttpUrl]
        selected_model: typing.Literal[tuple(e.name for e in AsrModels)] | None = Field(
            title="Speech-to-Text Provider",
            description="Choose a model to transcribe incoming audio messages to text.",
        )
        language: str | None

        input_prompt: str | None = Field(
            title="👩‍💻 Prompt",
            description="Optional prompt that the model can use as context to better understand the speech and maintain a consistent writing style.",
        )

        translation_model: (
            typing.Literal[tuple(e.name for e in TranslationModels)] | None
        )

        output_format: typing.Literal[tuple(e.name for e in AsrOutputFormat)] | None

        google_translate_target: str | None = Field(
            deprecated=True,
            description="use `translation_model` & `translation_target` instead.",
        )

    class RequestModel(TranslationOptions, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        raw_output_text: list[str] | None
        output_text: list[str | AsrOutputJson]

    def current_sr_to_session_state(self) -> dict:
        state = super().current_sr_to_session_state()
        google_translate_target = state.pop("google_translate_target", None)
        translation_model = state.get("translation_model")
        if google_translate_target and not translation_model:
            state["translation_model"] = TranslationModels.google.name
            state["translation_target"] = google_translate_target
        return state

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return [
            "selected_model",
            "language",
            "translation_model",
            "translation_target",
        ]

    @classmethod
    def get_run_title(cls, sr: SavedRun, pr: PublishedRun) -> str:
        import langcodes

        try:
            lang = langcodes.Language.get(sr.state["language"] or "").display_name()
        except (KeyError, langcodes.LanguageTagError):
            lang = None
        model = AsrModels.get(sr.state.get("selected_model"))
        lang_or_model = lang or (model and model.value)

        return " ".join(filter(None, [lang_or_model, cls.get_recipe_title()]))

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_ASR_META_IMG

    def preview_description(self, state: dict):
        return "Transcribe mp3, WhatsApp audio + wavs with OpenAI's Whisper or AI4Bharat / Bhashini ASR models. Optionally translate to any language too."

    def render_description(self):
        gui.markdown(
            """
            This workflow let's you compare the latest and finest speech recognition models from [OpenAI](https://openai.com/research/whisper), [AI4Bharat](https://ai4bharat.org) and [Bhashini](https://bhashini.gov.in) and Google's USM coming soon.
            """
        )
        gui.markdown(
            """
            Just upload an audio file (mp3, wav, ogg or aac file) setting its language and then choose a speech recognition engine. You can also translate the output to any language too (using Google's Translation APIs).
            """
        )

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.CompareLLM import CompareLLMPage
        from recipes.TextToSpeech import TextToSpeechPage

        from recipes.LipsyncTTS import LipsyncTTSPage

        return [
            VideoBotsPage,
            LipsyncTTSPage,
            TextToSpeechPage,
            CompareLLMPage,
        ]

    def render_form_v2(self):
        bulk_documents_uploader(
            "###### 🎙️ Audio Files",
            accept=("audio/*", "video/*", "application/octet-stream"),
        )

        self.render_speech_and_translation_inputs(asr_model_key="selected_model")

    @classmethod
    def render_speech_and_translation_inputs(cls, *, asr_model_key: str):
        selected_filter_language = language_filter_selector(
            options=asr_languages_without_dialects(),
        )

        col1, col2 = gui.columns(2)
        with col1:
            asr_model = asr_model_selector(
                label=f"###### {field_title(cls.RequestModel, 'selected_model')}",
                key=asr_model_key,
                language_filter=selected_filter_language,
            )
        with col2:
            asr_language_selector(asr_model, language_filter=selected_filter_language)

        if asr_model.supports_input_prompt():
            gui.text_area(
                f'###### {field_title_desc(cls.RequestModel, "input_prompt")}',
                key="input_prompt",
                value="Transcribe the recording as accurately as possible.",
                height=300,
            )

        if not gui.checkbox(
            "🔠 **Translate**",
            value=bool(gui.session_state.get("translation_model")),
        ):
            gui.session_state["translation_model"] = None
        else:
            gui.caption("Choose a model and language to translate recognized audio")
            col1, col2 = gui.columns(2)
            with col1:
                translation_model = translation_model_selector(
                    allow_none=False,
                    language_filter=selected_filter_language,
                    asr_model=asr_model,
                )
            with col2:
                translation_language_selector(
                    model=translation_model,
                    label=f"###### {field_title_desc(cls.RequestModel, 'translation_target')}",
                    key="translation_target",
                )

    def render_settings(self):
        self.render_translation_advanced_settings()

        enum_selector(
            AsrOutputFormat, label="###### Output Format", key="output_format"
        )

    @classmethod
    def render_translation_advanced_settings(cls):
        asr_model = AsrModels.get(gui.session_state.get("selected_model"))
        translation_model = TranslationModels.get(
            gui.session_state.get("translation_model")
        )
        if not translation_model:
            return

        # dont run translation if already translated using speech translation model
        if not (asr_model and asr_model.name == translation_model.name):
            selected_filter_language = gui.session_state.get("language_filter")
            translation_language_selector(
                model=translation_model,
                label=f"###### {field_title_desc(cls.RequestModel, 'translation_source')}",
                key="translation_source",
                allow_none=True,
                language_filter=selected_filter_language,
            )
        if translation_model.supports_glossary:
            gui.file_uploader(
                label=f"###### {field_title_desc(cls.RequestModel, 'glossary_document')}",
                key="glossary_document",
                accept=SUPPORTED_SPREADSHEET_TYPES,
            )

    def validate_form_v2(self):
        assert gui.session_state.get(
            "documents"
        ), "Please provide at least 1 Audio File"

    def render_output(self):
        text_outputs("**Transcription**", key="output_text", height=300)

    def render_example(self, state: dict):
        render_documents(state)
        text_outputs("**Transcription**", value=state.get("output_text"))

    def render_steps(self):
        if gui.session_state.get("translation_model"):
            col1, col2 = gui.columns(2)
            with col1:
                text_outputs("**Transcription**", key="raw_output_text")
            with col2:
                text_outputs("**Translation**", key="output_text")
        else:
            text_outputs("**Transcription**", key="output_text")

    def run(self, state: dict):
        # Parse Request
        request: AsrPage.RequestModel = self.RequestModel.parse_obj(state)

        selected_model = AsrModels[request.selected_model]
        translation_model = TranslationModels.get(request.translation_model)

        should_translate = translation_model and request.translation_target
        use_asr_speech_translation = (
            should_translate
            and translation_model.is_asr_model
            and selected_model.name == translation_model.name
        )

        yield f"Running {selected_model.value}..."
        asr_output = map_parallel(
            lambda audio: run_asr(
                audio_url=audio,
                selected_model=request.selected_model,
                language=request.language,
                output_format=request.output_format,
                speech_translation_target=(
                    request.translation_target if use_asr_speech_translation else None
                ),
                input_prompt=request.input_prompt,
            ),
            request.documents,
            max_workers=4,
        )

        if should_translate and not use_asr_speech_translation:
            # Save the raw ASR text for details view
            state["raw_output_text"] = asr_output
            # Run Translation
            yield f"Translating to {request.translation_target} using {translation_model.label}..."
            state["output_text"] = run_translate(
                asr_output,
                target_language=request.translation_target,
                source_language=forced_asr_languages.get(
                    selected_model, request.translation_source or request.language
                ),
                glossary_url=request.glossary_document,
                model=request.translation_model,
            )
        else:
            state["output_text"] = asr_output

    def get_cost_note(self) -> str | None:
        return "1 credit for 12.5 words ≈ 0.08 per word"

    def get_raw_price(self, state: dict):
        texts = state.get("output_text", [])
        total_words = sum(len(whitespace_re.split(str(out))) for out in texts)
        return 0.04 * total_words
