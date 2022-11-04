import json
import typing

import requests
import streamlit as st
from pydantic.main import BaseModel

from daras_ai.text_format import daras_ai_format_str
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model
from daras_ai_v2.text_training_data_widget import text_training_data, TrainingDataModel


class LetterWriterPage(BasePage):
    title = "Letter Writer"
    doc_name = "LetterWriter"
    endpoint = "/v1/LetterWriter/run"

    class RequestModel(BaseModel):
        action_id: str

        prompt_header: str = None
        example_letters: list[TrainingDataModel] = None

        lm_selected_api: str = None
        lm_selected_engine: str = None
        num_outputs: int = None
        quality: float = None
        lm_sampling_temperature: float = None

        api_http_method: str = None
        api_url: str = None
        api_headers: str = None
        api_json_body: str = None

        input_prompt: str = None
        strip_html_2_text: bool = False

        class Config:
            schema_extra = {
                "examples": {
                    "Basic": {
                        "value": {
                            "action_id": "14904",
                        }
                    },
                    "Custom example letters": {
                        "value": {
                            "action_id": "14904",
                            "example_letters": [
                                {
                                    "prompt": "Extreme weather events, both extreme cold and extreme heat will probably increase in frequency due to climate change.",
                                    "completion": "Dear Senate Rules Committee Members, Please pull HB 1620 out of the Rules Committee and send it for a floor vote",
                                }
                            ],
                        }
                    },
                }
            }

    class ResponseModel(BaseModel):
        output_letters: list[str]

        response_json: typing.Any
        generated_input_prompt: str
        final_prompt: str

    def render_description(self):
        st.write(
            """
            *ID > Call Custom API > Build Training Data > GPT3*
            
            This recipe is intended to help users see what would be an appropriate political letter they could 
            write to their elected officials, given a Bill number, talking points and desired outcomes for that bill. 
            It shows off how you can use Gooey.AI to -
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

            col1, col2 = st.columns(2, gap="medium")
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

            submitted = st.form_submit_button("🚀 Submit")
            return submitted

    def render_settings(self):
        st.write("### Model Settings")

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
            key="lm_sampling_temperature",
            min_value=0.0,
            max_value=1.0,
            value=1.0,
        )

        st.write("---")

        st.write("### Task description")
        st.write(
            """
            Briefly describe the task for the language model
            """
        )
        st.text_area(
            "prompt_header",
            label_visibility="collapsed",
            key="prompt_header",
            height=200,
        )

        st.write("---")

        st.write("### Example letters")

        st.write(
            """
            A set of example letters for the model to learn your writing style
            """
        )

        text_training_data("Talking points", "Letter", key="example_letters")

        st.write("---")

        st.write("### Custom API settings")

        st.write(
            """
        Call any external API to get the talking points from an input Action ID
         
        *You can substitute the user input Action ID like so - `{{ action_id }}`*
        """
        )

        col1, col2 = st.columns([1, 4])
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
            "Headers as JSON (optional)",
            key="api_headers",
        )
        st.text_area(
            "JSON Body (optional)",
            key="api_json_body",
        )

        st.write("---")

        st.write(
            """
        ##### Input Talking Points (Prompt)
        
        Specify the input prompt for the model.
        
        *You can use the powerful [glom](https://glom.readthedocs.io/en/latest/tutorial.html/) syntax to parse the API JSON response.*  
        *E.g. `This is my {{ "field.value" }}`*
        """
        )
        st.text_area(
            "input_prompt",
            label_visibility="collapsed",
            key="input_prompt",
        )
        st.checkbox("Strip all HTML -> Text?", key="strip_html_2_text")

    def run(self, state: dict) -> typing.Iterator[str | None]:
        yield "Calling API.."

        request = self.RequestModel.parse_obj(state)

        url = request.api_url.replace("{{ action_id }}", request.action_id)
        method = request.api_http_method.replace("{{ action_id }}", request.action_id)
        headers = request.api_headers.replace("{{ action_id }}", request.action_id)
        json_body = request.api_json_body.replace("{{ action_id }}", request.action_id)

        if not (url and method):
            raise ValueError("HTTP method / URL is empty. Please check your settings.")

        if headers:
            headers = json.loads(headers)
        else:
            headers = None

        if json_body:
            body = json.loads(json_body)
        else:
            body = None

        r = requests.request(method=method, url=url, headers=headers, json=body)
        r.raise_for_status()
        response_json = r.json()

        state["response_json"] = response_json
        yield "Generating Prompt..."

        if not request.input_prompt:
            raise ValueError("Input prompt is Empty. Please check your settings.")

        input_prompt = daras_ai_format_str(
            format_str=request.input_prompt,
            variables=response_json,
            do_html2text=request.strip_html_2_text,
        )

        state["generated_input_prompt"] = input_prompt
        yield "Generating Prompt..."

        if not request.prompt_header:
            raise ValueError(
                "Task description not provided. Please check your settings."
            )
        if not request.example_letters:
            raise ValueError(
                "Example letters not provided. Please check your settings."
            )

        prompt_prefix = "TalkingPoints:"
        completion_prefix = "Letter:"

        prompt_sep = "\n####\n"
        completion_sep = "\n$$$$\n"

        prompt_prefix = prompt_prefix.strip() + " "
        completion_prefix = completion_prefix.strip() + " "

        final_prompt = request.prompt_header.strip() + "\n\n"

        for value in request.example_letters:
            prompt_part = prompt_prefix + value.prompt + prompt_sep
            completion_part = completion_prefix + value.completion + completion_sep
            final_prompt += prompt_part + completion_part

        final_prompt += prompt_prefix + input_prompt + prompt_sep + completion_prefix

        state["final_prompt"] = final_prompt
        yield "Running Language Model..."

        state["output_letters"] = run_language_model(
            request.lm_selected_api,
            engine=request.lm_selected_engine,
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.lm_sampling_temperature,
            prompt=final_prompt,
            max_tokens=256,
            stop=[prompt_sep, completion_sep],
        )

    def render_output(self):
        st.write("### Generated Letters")
        output_letters = st.session_state.get(
            "output_letters",
            # this default value makes a nicer output while running :)
            [""] * st.session_state["num_outputs"],
        )
        for i, out in enumerate(output_letters):
            st.text_area(
                "output_letter",
                label_visibility="collapsed",
                help=f"output_letters {i}",
                value=out,
                height=300,
                disabled=True,
            )

        with st.expander("Steps"):
            response_json = st.session_state.get("response_json", {})
            st.write("**API Response**")
            st.json(
                response_json,
                expanded=False,
            )

            st.write("**Input Talking Points (Prompt)**")
            input_prompt = st.session_state.get("generated_input_prompt", "")
            st.text_area(
                "input_prompt",
                label_visibility="collapsed",
                value=input_prompt,
                disabled=True,
            )

            st.write("**Final Language Model Prompt**")
            final_prompt = st.session_state.get("final_prompt", "")
            st.text_area(
                "final_prompt",
                label_visibility="collapsed",
                value=final_prompt,
                disabled=True,
                height=300,
            )


if __name__ == "__main__":
    LetterWriterPage().render()
