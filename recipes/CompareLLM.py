import math
import random
import typing

import gooey_gui as gui
from pydantic import BaseModel

from ai_models.models import AIModelSpec
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model, SUPERSCRIPT
from daras_ai_v2.language_model_settings_widgets import (
    language_model_settings,
    LanguageModelSettings,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.variables_widget import render_prompt_vars


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
        input_prompt: str | None = None
        selected_models: str | None = None

    class RequestModel(LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_text: dict[str, list[str]]

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["input_prompt", "selected_models"]

    def render_form_v2(self):
        gui.code_editor(
            label="#### 👩‍💻 Prompt",
            key="input_prompt",
            language="jinja",
            style=dict(maxHeight="50vh"),
            help="Supports [Jinja](https://jinja.palletsprojects.com/en/stable/templates/) templating",
        )

        options = dict(
            AIModelSpec.objects.filter(category=AIModelSpec.Categories.llm).values_list(
                "name", "label"
            )
        )
        gui.multiselect(
            label="#### 🧠 Language Models",
            key="selected_models",
            options=options,
            format_func=options.__getitem__,
        )

        gui.markdown("#### 💪 Capabilities")
        # -- functions will render here in parent --

    def validate_form_v2(self):
        assert gui.session_state["input_prompt"], "Please enter a Prompt"
        assert gui.session_state["selected_models"], "Please select at least one model"

    def render_usage_guide(self):
        youtube_video("dhexRRDAuY8")

    def render_settings(self):
        language_model_settings(
            selected_models=gui.session_state.get("selected_models")
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: CompareLLMPage.RequestModel = self.RequestModel.model_validate(state)

        prompt = render_prompt_vars(request.input_prompt, state)
        state["output_text"] = output_text = {}

        for model in AIModelSpec.objects.filter(name__in=request.selected_models):
            yield f"Running {model.label}..."
            ret = run_language_model(
                model=model.name,
                quality=request.quality,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                prompt=prompt,
                max_tokens=request.max_tokens,
                avoid_repetition=request.avoid_repetition,
                response_format_type=request.response_format_type,
                reasoning_effort=request.reasoning_effort,
                stream=True,
            )
            for i, entries in enumerate(ret):
                output_text[model.name] = [e["content"] for e in entries]
                yield f"Streaming{str(i + 1).translate(SUPERSCRIPT)} {model.label}..."

    def render_output(self):
        _render_outputs(gui.session_state, 450)

    def render_run_preview_output(self, state: dict):
        col1, col2 = gui.columns(2)
        with col1:
            gui.write("**Prompt**")
            gui.write("```jinja2\n" + str(state.get("input_prompt") or "") + "\n```")
            variables = state.get("variables") or {}
            for key, value in variables.items():
                gui.text_area(f"`{key}`", value=str(value), disabled=True)
        with col2:
            _render_outputs(state, 300)

    def get_raw_price(self, state: dict) -> float:
        grouped_costs = self.get_grouped_linked_usage_cost_in_credits()
        price = sum(map(math.ceil, grouped_costs.values()))
        if "agrillm_qwen3_30b" in state.get("selected_models", []):
            price += 100

        return price + self.PROFIT_CREDITS

    def additional_notes(self) -> str | None:
        grouped_costs = self.get_grouped_linked_usage_cost_in_credits()
        if not grouped_costs:
            return
        parts = [
            f"{math.ceil(total)}Cr for {AIModelSpec.objects.get(name=model_name).label}"
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
                f"**{AIModelSpec.objects.get(name=key).label}**",
                help=f"output {key} {idx} {random.random()}",
                disabled=True,
                value=text,
                height=height,
            )
