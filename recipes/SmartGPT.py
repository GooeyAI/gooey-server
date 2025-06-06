import typing

import jinja2.sandbox
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import (
    LargeLanguageModels,
    run_language_model,
    CHATML_ROLE_USER,
    CHATML_ROLE_ASSISTANT,
)
from daras_ai_v2.language_model_settings_widgets import (
    language_model_settings,
    language_model_selector,
    LanguageModelSettings,
)
from daras_ai_v2.pt import PromptTree
from recipes.GoogleGPT import render_output_with_refs


class SmartGPTPage(BasePage):
    title = "SmartGPT"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ffd24ad8-88d7-11ee-a658-02420a000163/SmartGPT.png.png"
    workflow = Workflow.SMART_GPT
    slug_versions = ["SmartGPT"]
    price = 20

    class RequestModelBase(BasePage.RequestModel):
        input_prompt: str

        cot_prompt: str | None = None
        reflexion_prompt: str | None = None
        dera_prompt: str | None = None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        ) = None

    class RequestModel(LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_text: list[str]

        prompt_tree: PromptTree | None = None

    def render_form_v2(self):
        gui.text_area(
            """
            #### 👩‍💻 Prompt
            """,
            key="input_prompt",
            help="Why do birds sing?",
            height=100,
        )

    def render_settings(self):
        gui.text_area(
            """
##### Step 1: CoT Prompt
                """,
            key="cot_prompt",
        )
        gui.text_area(
            """
##### Step 2: Reflexion Prompt
                """,
            key="reflexion_prompt",
        )
        gui.text_area(
            """
##### Step 3: DERA Prompt 
                """,
            key="dera_prompt",
        )
        selected_model = language_model_selector()
        language_model_settings(selected_model)

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
        request: SmartGPTPage.RequestModel = self.RequestModel.model_validate(state)
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
            response_format_type=request.response_format_type,
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
                response_format_type=request.response_format_type,
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
            response_format_type=request.response_format_type,
        )
        state["output_text"] = dera_outputs

    def render_output(self):
        render_output_with_refs(gui.session_state)

    def render_run_preview_output(self, state: dict):
        gui.write("**Prompt**")
        gui.write("```properties\n" + state.get("input_prompt", "") + "\n```")
        render_output_with_refs(state, 200)

    def render_steps(self):
        prompt_tree = gui.session_state.get("prompt_tree", {})
        if prompt_tree:
            gui.write("**Prompt Tree**")
            gui.json(prompt_tree, expanded=True)

        output_text: list = gui.session_state.get("output_text", [])
        for idx, text in enumerate(output_text):
            gui.text_area(
                "**Output Text**",
                help=f"output {idx}",
                disabled=True,
                value=text,
            )


def answers_as_prompt(texts: list[str], sep="\n\n") -> str:
    return sep.join(
        f'''
[Answer {idx + 1}]: """
{text}
"""
'''.strip()
        for idx, text in enumerate(texts)
    )
