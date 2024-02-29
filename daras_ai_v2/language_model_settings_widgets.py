import gooey_ui as st
from daras_ai_v2.azure_doc_extract import azure_form_recognizer_models

from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc, field_desc
from daras_ai_v2.language_model import LargeLanguageModels


def language_model_settings(show_selector=True):
    st.write("##### 🔠 Language Model Settings")

    if show_selector:
        enum_selector(
            LargeLanguageModels,
            label_visibility="collapsed",
            key="selected_model",
            use_selectbox=True,
        )

    st.checkbox("Avoid Repetition", key="avoid_repetition")

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
    if (
        show_selector
        and not LargeLanguageModels[
            st.session_state.get("selected_model") or LargeLanguageModels.gpt_4.name
        ].is_chat_model()
    ):
        with col2:
            st.slider(
                label="""
###### Attempts
Generate multiple responses and choose the best one.
            """,
                key="quality",
                min_value=1.0,
                max_value=5.0,
                step=0.1,
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
