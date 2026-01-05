import gooey_gui as gui
from pydantic import BaseModel, Field

from ai_models.models import AIModelSpec, ModelProvider
from daras_ai_v2.enum_selector_widget import enum_selector, BLANK_OPTION
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.language_model import (
    ResponseFormatType,
    ReasoningEffort,
)


class LanguageModelSettings(BaseModel):
    avoid_repetition: bool | None = Field(
        None,
        title="Avoid Repetition",
        description="Avoid repeating the same words or phrases in the response.",
    )
    num_outputs: int | None = Field(
        None,
        title="Answer Outputs",
        description="How many answers should the copilot generate? Additional answer outputs increase the cost of each run.",
    )
    quality: float | None = Field(
        None,
        title="Attempts",
        description="Generate multiple responses and choose the best one",
    )
    max_tokens: int | None = Field(
        None,
        title="Max Output Tokens",
        description="The maximum number of tokens to generate in the completion. Increase to generate longer responses.",
    )
    sampling_temperature: float | None = Field(
        None,
        title="Creativity (aka Sampling Temperature)",
        description="Higher values allow the LLM to take more risks. Try values larger than 1 for more creative applications or 0 to ensure that LLM gives the same answer when given the same user input. ",
    )
    reasoning_effort: ReasoningEffort.api_choices | None = Field(
        None,
        title="Reasoning Effort",
        description=(
            "Constrains effort on reasoning for reasoning models. "
            "Increasing reasoning effort can improve response quality by enabling more thorough analysis for complex problems. "
            "Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning in a response. "
            "We suggest starting at the minimum and increasing the effort incrementally to find the optimal range for your use case"
        ),
    )
    response_format_type: ResponseFormatType | None = Field(
        None, title="Response Format"
    )


def language_model_selector(
    label: str = "##### 🔠 Language Model Settings",
    label_visibility: str = "visible",
    key: str = "selected_model",
):
    options = dict(
        AIModelSpec.objects.filter(category=AIModelSpec.Categories.llm)
        .exclude_deprecated(selected_models=gui.session_state.get(key))
        .values_list("name", "label")
    )
    return gui.selectbox(
        options=options,
        format_func=options.__getitem__,
        label=label,
        label_visibility=label_visibility,
        key=key,
    )


def language_model_settings(selected_models: str | list[str] | None = None) -> None:
    if isinstance(selected_models, str):
        selected_models = [selected_models]
    elif not selected_models:
        selected_models = []

    llms = list(AIModelSpec.objects.filter(name__in=selected_models))

    col1, col2 = gui.columns(2)
    with col1:
        gui.checkbox(
            label="**" + field_title(LanguageModelSettings, "avoid_repetition") + "**",
            help=field_desc(LanguageModelSettings, "avoid_repetition"),
            key="avoid_repetition",
        )

    with col2:
        gui.selectbox(
            label=(
                "###### " + field_title(LanguageModelSettings, "response_format_type")
            ),
            help=field_desc(LanguageModelSettings, "response_format_type"),
            options=[None, "json_object"],
            key="response_format_type",
            format_func={
                None: BLANK_OPTION,
                "json_object": "JSON Object",
            }.__getitem__,
        )

    col1, col2 = gui.columns(2)
    with col1:
        if llms:
            max_output_tokens = min(
                llm.llm_max_output_tokens or llm.llm_context_window for llm in llms
            )
        else:
            max_output_tokens = 4096

        gui.slider(
            label="###### " + field_title(LanguageModelSettings, "max_tokens"),
            help=field_desc(LanguageModelSettings, "max_tokens"),
            key="max_tokens",
            min_value=10,
            max_value=max_output_tokens,
            step=2,
        )

    if any(llm.llm_supports_temperature for llm in llms):
        with col2:
            gui.slider(
                label=(
                    "###### "
                    + field_title(LanguageModelSettings, "sampling_temperature")
                ),
                help=field_desc(LanguageModelSettings, "sampling_temperature"),
                key="sampling_temperature",
                min_value=0.0,
                max_value=2.0,
            )

    col1, col2 = gui.columns(2)
    with col1:
        gui.slider(
            label="###### " + field_title(LanguageModelSettings, "num_outputs"),
            help=field_desc(LanguageModelSettings, "num_outputs"),
            key="num_outputs",
            min_value=1,
            max_value=4,
        )
    if any(
        not llm.llm_is_chat_model and llm.provider == ModelProvider.openai
        for llm in llms
    ):
        with col2:
            gui.slider(
                label="###### " + field_title(LanguageModelSettings, "quality"),
                help=field_desc(LanguageModelSettings, "quality"),
                key="quality",
                min_value=1.0,
                max_value=5.0,
                step=0.1,
            )

    if any(llm.llm_is_thinking_model for llm in llms):
        col1, _ = gui.columns(2)
        with col1:
            enum_selector(
                ReasoningEffort,
                label=(
                    "###### " + field_title(LanguageModelSettings, "reasoning_effort")
                ),
                help=field_desc(LanguageModelSettings, "reasoning_effort"),
                key="reasoning_effort",
                use_selectbox=True,
                allow_none=True,
            )
