from pydantic import BaseModel, Field

import gooey_ui as st
from daras_ai_v2.enum_selector_widget import enum_selector, BLANK_OPTION
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.language_model import LargeLanguageModels, ResponseFormatType, LLMApis


class LanguageModelSettings(BaseModel):
    avoid_repetition: bool | None
    num_outputs: int | None
    quality: float | None
    max_tokens: int | None
    sampling_temperature: float | None
    response_format_type: ResponseFormatType = Field(
        None,
        title="Response Format",
    )


def language_model_selector(
    label: str = "##### 🔠 Language Model Settings",
    label_visibility: str = "visible",
    key: str = "selected_model",
):
    return enum_selector(
        LargeLanguageModels,
        label=label,
        label_visibility=label_visibility,
        key=key,
        use_selectbox=True,
    )


def language_model_settings(selected_model: str = None):
    try:
        llm = LargeLanguageModels[selected_model]
    except KeyError:
        llm = None

    col1, col2 = st.columns(2)
    with col1:
        st.checkbox("Avoid Repetition", key="avoid_repetition")
    if not llm or llm.supports_json:
        with col2:
            st.selectbox(
                f"###### {field_title_desc(LanguageModelSettings, 'response_format_type')}",
                options=[None, "json_object"],
                key="response_format_type",
                format_func={
                    None: BLANK_OPTION,
                    "json_object": "JSON Object",
                }.__getitem__,
            )

    col1, col2 = st.columns(2)
    with col1:
        st.number_input(
            label="""
            ###### Max Output Tokens
            The maximum number of tokens to generate in the completion. Increase to generate longer responses.
            """,
            key="max_tokens",
            min_value=10,
            step=10,
        )
    with col2:
        st.slider(
            label="""
            ###### Creativity (aka Sampling Temperature)
    
            Higher values allow the LLM to take more risks. Try values larger than 1 for more creative applications or 0 to ensure that LLM gives the same answer when given the same user input. 
            """,
            key="sampling_temperature",
            min_value=0.0,
            max_value=2.0,
        )

    col1, col2 = st.columns(2)
    with col1:
        st.slider(
            label="""
###### Answer Outputs
How many answers should the copilot generate? Additional answer outputs increase the cost of each run.
            """,
            key="num_outputs",
            min_value=1,
            max_value=4,
        )
    if llm and not llm.is_chat_model and llm.llm_api == LLMApis.openai:
        with col2:
            st.slider(
                label="""
###### Attempts
Generate multiple responses and choose the best one
                """,
                key="quality",
                min_value=1.0,
                max_value=5.0,
                step=0.1,
            )
