import typing

import jinja2.sandbox
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from recipes.GoogleGPT import render_output_with_refs
from daras_ai_v2.base import BasePage
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import (
    LargeLanguageModels,
    run_language_model,
    CHATML_ROLE_USER,
    CHATML_ROLE_ASSISTANT,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.pt import PromptTree

DEFAULT_SMARTGPT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/3d71b434-9457-11ee-8edd-02420a0001c7/Smart%20GPT.jpg.png"


class SmartGPTPage(BasePage):
    title = "SmartGPT"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ffd24ad8-88d7-11ee-a658-02420a000163/SmartGPT.png.png"
    workflow = Workflow.SMART_GPT
    slug_versions = ["SmartGPT"]
    price = 20

    class RequestModel(BaseModel):
        input_prompt: str

        cot_prompt: str | None
        reflexion_prompt: str | None
        dera_prompt: str | None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

    class ResponseModel(BaseModel):
        output_text: list[str]

        prompt_tree: PromptTree | None

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_SMARTGPT_META_IMG

    def render_form_v2(self):
        st.text_area(
            """
            #### 👩‍💻 Prompt
            """,
            key="input_prompt",
            help="Why do birds sing?",
            height=100,
        )

    def render_settings(self):
        st.text_area(
            """
##### Step 1: CoT Prompt
                """,
            key="cot_prompt",
            height=150,
        )
        st.text_area(
            """
##### Step 2: Reflexion Prompt
                """,
            key="reflexion_prompt",
            height=150,
        )
        st.text_area(
            """
##### Step 3: DERA Prompt 
                """,
            key="dera_prompt",
            height=150,
        )
        language_model_settings()

    def related_workflows(self):
        from recipes.CompareLLM import CompareLLMPage
        from recipes.DocSearch import DocSearchPage
        from recipes.DocSummary import DocSummaryPage
        from recipes.GoogleGPT import GoogleGPTPage

        return [
            CompareLLMPage,
            DocSearchPage,
            GoogleGPTPage,
            DocSummaryPage,
        ]

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: SmartGPTPage.RequestModel = self.RequestModel.parse_obj(state)
        jinja_env = jinja2.sandbox.SandboxedEnvironment()
        cot_prompt = jinja_env.from_string(request.cot_prompt).render(
            input_prompt=request.input_prompt.strip()
        )
        state["prompt_tree"] = prompt_tree = [
            {
                "prompt": [
                    {"role": CHATML_ROLE_USER, "content": cot_prompt},
                ],
                "children": [],
            },
        ]
        yield "Running CoT Prompt..."
        cot_outputs = run_language_model(
            messages=(prompt_tree[0]["prompt"]),
            model=request.selected_model,
            max_tokens=request.max_tokens,
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
        )
        state["prompt_tree"] = prompt_tree = [
            {
                "prompt": [
                    {"role": CHATML_ROLE_USER, "content": cot_prompt},
                    {"role": CHATML_ROLE_ASSISTANT, "content": cot_out},
                    {"role": CHATML_ROLE_USER, "content": request.reflexion_prompt},
                ],
                "children": prompt_tree,
            }
            for cot_out in cot_outputs
        ]
        yield "Running Reflexion Prompt(s)..."
        reflexion_outputs = map_parallel(
            lambda node: run_language_model(
                messages=(node["prompt"]),
                model=request.selected_model,
                max_tokens=request.max_tokens,
                quality=request.quality,
                temperature=request.sampling_temperature,
                avoid_repetition=request.avoid_repetition,
            )[0],
            prompt_tree,
        )
        state["prompt_tree"] = prompt_tree = [
            {
                "prompt": [
                    {"role": CHATML_ROLE_USER, "content": cot_prompt},
                    {
                        "role": CHATML_ROLE_ASSISTANT,
                        "content": answers_as_prompt(cot_outputs),
                    },
                    {
                        "role": CHATML_ROLE_ASSISTANT,
                        "content": request.reflexion_prompt,
                    },
                    {
                        "role": CHATML_ROLE_ASSISTANT,
                        "content": answers_as_prompt(reflexion_outputs),
                    },
                    {"role": CHATML_ROLE_USER, "content": request.dera_prompt},
                ],
                "children": prompt_tree,
            }
        ]
        yield "Running DERA Prompt..."
        dera_outputs = run_language_model(
            messages=(prompt_tree[0]["prompt"]),
            model=request.selected_model,
            max_tokens=request.max_tokens,
            quality=request.quality,
            temperature=request.sampling_temperature,
            avoid_repetition=request.avoid_repetition,
        )
        state["output_text"] = dera_outputs

    def render_output(self):
        render_output_with_refs(st.session_state, 300)

    def render_example(self, state: dict):
        st.write("**Prompt**")
        st.write("```properties\n" + state.get("input_prompt", "") + "\n```")
        render_output_with_refs(state, 200)

    def render_steps(self):
        prompt_tree = st.session_state.get("prompt_tree", {})
        if prompt_tree:
            st.write("**Prompt Tree**")
            st.json(prompt_tree, expanded=True)

        output_text: list = st.session_state.get("output_text", [])
        for idx, text in enumerate(output_text):
            st.text_area(
                f"**Output Text**",
                help=f"output {idx}",
                disabled=True,
                value=text,
                height=200,
            )

    def preview_description(self, state: dict) -> str:
        return "SmartGPT is a cutting-edge AI technology that can be used to generate natural language responses to any given input. We have combined the power of [CoT](https://arxiv.org/abs/2305.02897), [Reflexion](https://arxiv.org/abs/2303.11366) & [DERA](https://arxiv.org/abs/2303.17071) into one pipeline so that you can use ChatGPT to its full potential! Input your prompt + a reflection/research prompt + a resolver prompt to use SmartGPT for enhanced text generation, natural language and incredible question-answer results."

    def get_raw_price(self, state: dict) -> float:
        return self.price * state.get("num_outputs", 1)


def answers_as_prompt(texts: list[str], sep="\n\n") -> str:
    return sep.join(
        f'''
[Answer {idx + 1}]: """
{text}
"""
'''.strip()
        for idx, text in enumerate(texts)
    )
