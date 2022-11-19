import re
import typing
import requests

from pydantic import BaseModel
import streamlit as st
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model

email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


class SocialLookupEmail(BasePage):
    title = "Get Your Emails Actually Read"
    slug = "SocialLookupEmail"

    class RequestModel(BaseModel):
        input_prompt: str
        email_address: str

        sampling_temperature: float = 1.0
        max_tokens: int = 1024

        class Config:
            schema_extra = {
                "example": {
                    "input_prompt": "This is a sample email",
                    "email_address": "sean@dara.network",
                }
            }

    class ResponseModel(BaseModel):
        gpt3_output: str

    def render_description(self):
        st.write(
            """
    This recipe takes an email address and a sample email body. It attempts to pull the social profile of the email address and then personlize the email using AI.

    How It Works:

    1. Calls social media APIs to get a user's social profile from twitter, facebook, linkedin and/or insta. 
    2. Inserts relevant parts of the profile (e.g. city, previous workplaces) into the email.
    3. Send the email to OpenAI to craft a great, personalized email
    
     *EmailID > Profile > Email Template > GPT3 > Email*  

    """
        )

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
            value=.7,
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
                ### Email Address
                Give us an email address and we'll try to get determine the profile data associated with it
                """
            )
            st.text_input(
                "email_address",
                label_visibility="collapsed",
                key="email_address",
                placeholder="john@appleseed.com",
            )
            st.caption(
                "By providing an email address, you agree to Gooey.AI's [Privacy Policy](https://dara.network/privacy)"
            )

            st.write(
                """
                ### Email Body
                """
            )
            st.text_area(
                "input_prompt",
                label_visibility="collapsed",
                key="input_prompt",
                height=200,
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        if submitted:
            text_prompt = st.session_state.get("input_prompt")
            email_address = st.session_state.get("email_address")
            if not (text_prompt and email_address):
                st.error("Please provide a Prompt and an Email Address", icon="⚠️")
                return False

            if not re.fullmatch(email_regex, email_address):
                st.error("Please provide a valid Email Address", icon="⚠️")
                return False

        return submitted

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        #yield "Fetching profile data..."
        #person = get_profile_for_email(request.email_address)
        #if person:
        #    yield "Found profile data..."
        #    state["person"] = person

            #yield from super().run(state)

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
            ### Email Body Output 
            """
        )
        st.text_area(
            "Output",
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
            st.write("**GPT-3**")
            st.write(state.get("gpt3_output", ""))

@st.cache()
def get_profile_for_email(email_address):
    r = requests.post(
        "https://api.apollo.io/v1/people/match",
        json={
            "api_key": "BOlC1SGQWNuP3D70WA_-yw",
            "email": email_address,
        },
    )
    r.raise_for_status()

    person = r.json()["person"]
    if not person:
        return

    return person


if __name__ == "__main__":
    SocialLookupEmail().render()
