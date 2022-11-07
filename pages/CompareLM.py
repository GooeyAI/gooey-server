import typing

from pydantic import BaseModel
import streamlit as st
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model


class CompareLMPage(BasePage):
    title = "GPT3 vs Flan-T5"
    doc_name = "CompareLM"
    endpoint = "/v1/CompareLM/run"

    class RequestModel(BaseModel):
        input_prompt: str
        sampling_temperature: float = 1.0
        max_tokens: int = 256

    class ResponseModel(BaseModel):
        gpt3_output: str
        flan_t5_output: str

    def render_settings(self):
        st.write(
            """
            ##### Model Risk Factor 

            *(Sampling Temperature)*

            Higher values allow the model to take more risks.
            Try 0.9 for more creative applications, 
            and 0 for ones with a well-defined answer. 
            """
        )
        st.slider(
            label="model risk",
            label_visibility="collapsed",
            key="sampling_temperature",
            min_value=0.0,
            max_value=1.0,
            value=1.0,
        )

        st.write(
            """
            #### Max Output Tokens
            The maximum number of [tokens](https://beta.openai.com/tokenizer) to generate in the completion.
            """
        )
        st.number_input(
            label="max_tokens",
            label_visibility="collapsed",
            key="max_tokens",
            min_value=1,
            max_value=4096,
        )

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write(
                """
                ### Prompt
                """
            )
            st.text_area(
                "input_prompt",
                label_visibility="collapsed",
                key="input_prompt",
                height=200,
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        return submitted

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        yield "Running Flan-T5..."
        state["flan_t5_output"] = run_language_model(
            api_provider="flan-t5",
            engine="",
            quality=1,
            num_outputs=1,
            temperature=request.sampling_temperature,
            prompt=request.input_prompt,
            max_tokens=request.max_tokens,
            stop=None,
        )[0]

        yield "Running GPT-3..."
        state["gpt3_output"] = run_language_model(
            api_provider="openai",
            engine="text-davinci-002",
            quality=1,
            num_outputs=1,
            temperature=request.sampling_temperature,
            prompt=request.input_prompt,
            max_tokens=request.max_tokens,
            stop=None,
        )[0]

    def render_output(self):
        st.write(
            """
            ### Flan-T5 
            [`flan-t5-xxl`](https://huggingface.co/google/flan-t5-xxl)
            """
        )
        st.text_area(
            "flan_t5_output",
            label_visibility="collapsed",
            value=st.session_state.get("flan_t5_output", ""),
            disabled=True,
            height=200,
        )

        st.write(
            """
            ### GPT-3 
            [`text-davinci-002`](https://beta.openai.com/docs/models/gpt-3)
            """
        )
        st.text_area(
            "gpt3_output",
            label_visibility="collapsed",
            disabled=True,
            value=st.session_state.get("gpt3_output", ""),
            height=200,
        )

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.write(state.get("input_prompt", ""))
        with col2:
            st.write("**Flan-T5**")
            st.write(state.get("flan_t5_output", ""))
            st.write("**GPT-3**")
            st.write(state.get("gpt3_output", ""))


if __name__ == "__main__":
    CompareLMPage().render()
