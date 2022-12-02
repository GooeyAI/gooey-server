import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model


class CompareLMPage(BasePage):
    title = "Compare Text LLMs: GPT3 vs Flan-T5"
    slug = "CompareLM"

    class RequestModel(BaseModel):
        input_prompt: str
        sampling_temperature: float | None
        max_tokens: int | None

    class ResponseModel(BaseModel):
        gpt3_output: str
        flan_t5_output: str

    def render_description(self):
        st.write(
            """
                This recipe takes any prompt and then passes it both OpenAI's GPT3 and Google's FLAN-T5 text generation engines.
            """
        )

    def render_settings(self):
        st.slider(
            """
            ##### Model Risk Factor 

            *(Sampling Temperature)*

            Higher values allow the model to take more risks.
            Try 0.9 for more creative applications, 
            and 0 for ones with a well-defined answer. 
            """,
            key="sampling_temperature",
            min_value=0.0,
            max_value=1.0,
            value=1.0,
        )

        st.number_input(
            """
            #### Max Output Tokens
            The maximum number of [tokens](https://beta.openai.com/tokenizer) to generate in the completion.
            """,
            key="max_tokens",
            min_value=1,
            max_value=4096,
        )

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.text_area(
                """
                ### Prompt
                """,
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
        st.text_area(
            """
            ### Flan-T5 
            [`flan-t5-xxl`](https://huggingface.co/google/flan-t5-xxl)
            """,
            value=st.session_state.get("flan_t5_output", ""),
            disabled=True,
            height=200,
        )

        st.text_area(
            """
            ### GPT-3 
            [`text-davinci-002`](https://beta.openai.com/docs/models/gpt-3)
            """,
            disabled=True,
            value=st.session_state.get("gpt3_output", ""),
            height=200,
        )

    def render_example(self, state: dict):
        st.markdown("```" + state.get("input_prompt", "").replace("\n", "") + "```")

        col1, col2 = st.columns(2)
        with col1:
            st.write("**Flan-T5**")
            st.write(state.get("flan_t5_output", ""))
        with col2:
            st.write("**GPT-3**")
            st.write(state.get("gpt3_output", ""))


if __name__ == "__main__":
    CompareLMPage().render()
