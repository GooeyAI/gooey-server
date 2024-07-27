import math
import random
import typing

from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.language_model import (
    run_language_model,
    LargeLanguageModels,
    SUPERSCRIPT,
    ResponseFormatType,
)
from daras_ai_v2.language_model_settings_widgets import (
    language_model_settings,
    LanguageModelSettings,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.prompt_vars import render_prompt_vars

DEFAULT_COMPARE_LM_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/fef06d86-1f70-11ef-b8ee-02420a00015b/LLMs.jpg"


class CompareLLMPage(BasePage):
    PROFIT_CREDITS = 1

    title = "Large Language Models: GPT-3"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ae42015e-88d7-11ee-aac9-02420a00016b/Compare%20LLMs.png.png"
    workflow = Workflow.COMPARE_LLM
    slug_versions = ["CompareLLM", "llm", "compare-large-language-models"]

    functions_in_settings = False

    sane_defaults = {
        "avoid_repetition": False,
        "num_outputs": 1,
        "quality": 1.0,
        "max_tokens": 500,
        "sampling_temperature": 0.7,
    }

    class RequestModelBase(BasePage.RequestModel):
        input_prompt: str | None
        selected_models: (
            list[typing.Literal[tuple(e.name for e in LargeLanguageModels)]] | None
        )

    class RequestModel(LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_text: dict[
            typing.Literal[tuple(e.name for e in LargeLanguageModels)], list[str]
        ]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_COMPARE_LM_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Which language model works best your prompt? Compare your text generations across multiple large language models (LLMs) like OpenAI's evolving and latest ChatGPT engines and others like Curie, Ada, Babbage."

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["input_prompt", "selected_models"]

    def render_form_v2(self):
        gui.text_area(
            """
            #### 👩‍💻 Prompt
            """,
            key="input_prompt",
            help="What a fine day..",
            height=300,
        )

        enum_multiselect(
            LargeLanguageModels,
            label="#### 🤗 Compare Language Models",
            key="selected_models",
            checkboxes=False,
        )

    def validate_form_v2(self):
        assert gui.session_state["input_prompt"], "Please enter a Prompt"
        assert gui.session_state["selected_models"], "Please select at least one model"

    def render_usage_guide(self):
        youtube_video("dhexRRDAuY8")

    def render_settings(self):
        language_model_settings()

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: CompareLLMPage.RequestModel = self.RequestModel.parse_obj(state)

        prompt = render_prompt_vars(request.input_prompt, state)
        state["output_text"] = output_text = {}

        for selected_model in request.selected_models:
            model = LargeLanguageModels[selected_model]
            yield f"Running {model.value}..."
            ret = run_language_model(
                model=selected_model,
                quality=request.quality,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                prompt=prompt,
                max_tokens=request.max_tokens,
                avoid_repetition=request.avoid_repetition,
                response_format_type=request.response_format_type,
                stream=True,
            )
            for i, entries in enumerate(ret):
                output_text[selected_model] = [e["content"] for e in entries]
                yield f"Streaming{str(i + 1).translate(SUPERSCRIPT)} {model.value}..."

    def render_output(self):
        _render_outputs(gui.session_state, 450)

    def render_example(self, state: dict):
        col1, col2 = gui.columns(2)
        with col1:
            gui.write("**Prompt**")
            gui.write("```jinja2\n" + state.get("input_prompt", "") + "\n```")
            for key, value in state.get("variables", {}).items():
                gui.text_area(f"`{key}`", value=str(value), disabled=True)
        with col2:
            _render_outputs(state, 300)

    def get_raw_price(self, state: dict) -> float:
        grouped_costs = self.get_grouped_linked_usage_cost_in_credits()
        return sum(map(math.ceil, grouped_costs.values())) + self.PROFIT_CREDITS

    def additional_notes(self) -> str | None:
        grouped_costs = self.get_grouped_linked_usage_cost_in_credits()
        if not grouped_costs:
            return
        parts = [
            f"{math.ceil(total)}Cr for {LargeLanguageModels[model_name].value}"
            for model_name, total in grouped_costs.items()
        ]
        return f"\n*Breakdown: {' + '.join(parts)} + {self.PROFIT_CREDITS}Cr/run*"

    def related_workflows(self) -> list:
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.SocialLookupEmail import SocialLookupEmailPage
        from recipes.VideoBots import VideoBotsPage
        from recipes.LipsyncTTS import LipsyncTTSPage

        return [
            SEOSummaryPage,
            SocialLookupEmailPage,
            VideoBotsPage,
            LipsyncTTSPage,
        ]


def _render_outputs(state, height):
    selected_models = state.get("selected_models", [])
    for key in selected_models:
        output_text: dict = state.get("output_text", {}).get(key, [])
        for idx, text in enumerate(output_text):
            gui.text_area(
                f"**{LargeLanguageModels[key].value}**",
                help=f"output {key} {idx} {random.random()}",
                disabled=True,
                value=text,
                height=height,
            )
