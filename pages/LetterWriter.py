import typing

import streamlit as st
from pydantic.main import BaseModel

from daras_ai_v2.base import DarsAiPage, get_saved_doc, get_doc_ref, set_saved_doc
from daras_ai_v2.text_training_data_widget import text_training_data, TrainingDataSchema


class LetterWriterPage(DarsAiPage):
    title = "Letter Writer"
    doc_name = "LetterWriter"
    endpoint = "/v1/LetterWriter/run"

    class RequestModel(BaseModel):
        action_id: str

        prompt_header: str = None
        example_letters: TrainingDataSchema = None

        num_outputs: int = None
        quality: float = None
        sampling_temperature: float = None

        api_http_method: str = None
        api_url: str = None
        api_headers: str = None
        api_json_body: str = None
        api_output_formatter: str = None

        class Config:
            schema_extra = {
                "example": {
                    "action_id": "14904",
                }
            }

    class ResponseModel(BaseModel):
        output_letters: list[str]

    def render_description(self):
        st.write(
            """
            *ID > Call Custom API > Build Training Data > GPT3*
            
            This recipe is intended to help users see what would be an appropriate political letter they could 
            write to their elected officials, given a Bill number, talking points and desired outcomes for that bill. 
            It shows off how you can use Daras.AI to -
            1. Get a parameter (e.g. the Action ID)
            2. Call any API (e.g the takeaction.network's API that return talking points associated with a bill) 
            3. Then merge this data with a GPT3 prompt to create a sample political letter. 
            """
        )

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write("### Action ID")
            st.text_input(
                "action_id",
                key="action_id",
                label_visibility="collapsed",
            )

            submitted = st.form_submit_button("🚀 Submit")
            return submitted

    def render_settings(self):
        st.write(
            """
            #### Task description
            Breiefly describe the task for the language model
            """
        )
        st.text_area(
            "prompt_header",
            label_visibility="collapsed",
            key="prompt_header",
            height=200,
        )

        st.write("---")

        st.write(
            """
            #### Example letters
            A set of example letters so that the model can learn your writing style
            """
        )

        text_training_data("Talking points", "Letter", key="example_letters")

        st.write("---")

        st.write("### Model Params")

        col1, col2 = st.columns(2)

        with col1:
            # select text api
            api_provider_options = ["openai", "goose.ai"]
            api_provider = st.selectbox(
                label="Language Model Provider",
                options=api_provider_options,
                key="lm_selected_api",
            )

        # set api key
        match api_provider:
            case "openai":
                engine_choices = [
                    "text-davinci-002",
                    "text-curie-001",
                    "text-babbage-001",
                    "text-ada-001",
                ]
            case "goose.ai":
                engine_choices = [
                    "gpt-neo-20b",
                    "cassandra-lit-2-7b",
                    "cassandra-lit-e2-2-7b",
                    "cassandra-lit-e3-2-7b",
                    "cassandra-lit-6-7b",
                    "cassandra-lit-e2-6-7b",
                    "cassandra-lit-e3-6-7b",
                    "convo-6b",
                    "fairseq-125m",
                    "fairseq-355m",
                    "fairseq-1-3b",
                    "fairseq-2-7b",
                    "fairseq-6-7b",
                    "fairseq-13b",
                    "gpt-j-6b",
                    "gpt-neo-125m",
                    "gpt-neo-1-3b",
                    "gpt-neo-2-7b",
                ]
            case _:
                raise ValueError()

        with col2:
            st.selectbox(
                label="Engine",
                options=engine_choices,
                key="lm_selected_engine",
            )

        with col1:
            st.slider(
                label="# of Outputs",
                key="num_outputs",
                min_value=1,
                max_value=4,
                value=1,
            )
        with col2:
            st.slider(
                label="Quality",
                key="quality",
                min_value=1.0,
                max_value=5.0,
                step=0.1,
                value=1.0,
            )

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

        st.write("---")

        st.write("### Custom API settings")

        col1, col2 = st.columns([1, 3])
        with col1:
            st.text_input(
                "HTTP Method",
                key="api_http_method",
            )
        with col2:
            st.text_input(
                "URL",
                key="api_url",
            )
        st.text_area(
            "Headers",
            key="api_headers",
        )
        st.text_area(
            "JSON Body",
            key="api_json_body",
        )
        st.text_area(
            "Output Formatter",
            key="api_output_formatter",
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        yield "Calling API.."

        yield "Running GPT3..."


if __name__ == "__main__":
    LetterWriterPage().render()
