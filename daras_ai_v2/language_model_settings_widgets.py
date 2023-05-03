import streamlit2 as st

from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.language_model import LargeLanguageModels


def language_model_settings(show_selector=True):
    st.write("##### 🔠 Language Model Settings")

    if show_selector:
        enum_selector(
            LargeLanguageModels,
            label_visibility="collapsed",
            key="selected_model",
        )

    st.checkbox("Avoid Repetition", key="avoid_repetition")

    col1, col2 = st.columns(2)
    with col1:
        st.slider(
            label="""
###### Number of Outputs
How many completion choices to generate for each input
            """,
            key="num_outputs",
            min_value=1,
            max_value=4,
        )
    if (
        show_selector
        and st.session_state.get("selected_model")
        != LargeLanguageModels.gpt_3_5_turbo.name
    ):
        with col2:
            st.slider(
                label="""
###### Quality
*(Not applicable for ChatGPT)*
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
            ###### Output Size
            *The maximum number of [tokens](https://beta.openai.com/tokenizer) to generate in the completion.*
            """,
            key="max_tokens",
            min_value=10,
            step=10,
        )
    with col2:
        st.slider(
            label="""
            ###### Model Creativity 
            *(Sampling Temperature)*
    
            Higher values allow the model to take more risks.
            Try 0.9 for more creative applications, 
            and 0 for ones with a well-defined answer. 
            """,
            key="sampling_temperature",
            min_value=0.0,
            max_value=1.0,
        )
