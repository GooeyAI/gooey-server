import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.language_model import run_language_model, LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings

DEFAULT_COMPARE_LM_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/compare%20llm%20under%201%20mg%20gif.gif"


class CompareLLMPage(BasePage):
    title = "Large Language Models: GPT-3"
    slug_versions = ["CompareLLM", "compare-large-language-models"]

    sane_defaults = {
        "avoid_repetition": False,
        "num_outputs": 1,
        "quality": 1.0,
        "max_tokens": 500,
        "sampling_temperature": 0.7,
    }

    class RequestModel(BaseModel):
        input_prompt: str
        selected_models: list[
            typing.Literal[tuple(e.name for e in LargeLanguageModels)]
        ] | None

        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

    class ResponseModel(BaseModel):
        output_text: dict[
            typing.Literal[tuple(e.name for e in LargeLanguageModels)], list[str]
        ]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_COMPARE_LM_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Which language model works best your prompt? Compare OpenAI GPT3 engines (davinci vs curie) with more LLMs being added soon. Pay with Stripe or PayPal"

    def render_form_v2(self):
        st.text_area(
            """
            #### 👩‍💻 Prompt
            *Supports [ChatML](https://github.com/openai/openai-python/blob/main/chatml.md)*
            """,
            key="input_prompt",
            help="What a fine day..",
            height=400,
        )
        enum_multiselect(
            LargeLanguageModels,
            label="#### 🤗 Compare Langugage Models",
            key="selected_models",
        )

    def validate_form_v2(self):
        assert st.session_state["input_prompt"], "Please enter a Prompt"
        assert st.session_state["selected_models"], "Please select at least one model"

    def render_settings(self):
        language_model_settings(show_selector=False)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: CompareLLMPage.RequestModel = self.RequestModel.parse_obj(state)

        state["output_text"] = output_text = {}

        for selected_model in request.selected_models:
            yield f"Running {LargeLanguageModels[selected_model].value}..."

            output_text[selected_model] = run_language_model(
                model=selected_model,
                quality=request.quality,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                prompt=request.input_prompt,
                max_tokens=request.max_tokens,
                avoid_repetition=request.avoid_repetition,
            )

    def render_output(self):
        self._render_outputs(st.session_state, 450)

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Prompt**")
            st.write("```properties\n" + state.get("input_prompt", "") + "\n```")
        with col2:
            self._render_outputs(state, 300)

    def _render_outputs(self, state, height):
        selected_models = state.get("selected_models", [])
        for key in selected_models:
            output_text: dict = state.get("output_text", {}).get(key, [])
            for idx, text in enumerate(output_text):
                st.text_area(
                    f"**{LargeLanguageModels[key].value}**",
                    help=f"output {key} {idx}",
                    disabled=True,
                    value=text,
                    height=height,
                )

    def get_price(self) -> int:
        selected_models = st.session_state.get("selected_models", [])
        total = 0
        for name in selected_models:
            match name:
                case LargeLanguageModels.gpt_3_5_turbo.name:
                    total += 1
                case LargeLanguageModels.text_davinci_003.name | LargeLanguageModels.code_davinci_002.name:
                    total += 10
                case LargeLanguageModels.text_curie_001.name:
                    total += 5
                case LargeLanguageModels.text_babbage_001.name:
                    total += 2
                case LargeLanguageModels.text_ada_001.name:
                    total += 1
        return total

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


if __name__ == "__main__":
    CompareLLMPage().render()
