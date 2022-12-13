import re
import typing
import requests

from pydantic import BaseModel
import streamlit as st

from daras_ai.text_format import daras_ai_format_str
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model

email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


class SocialLookupEmailPage(BasePage):
    title = "Get Your Emails Actually Read"
    slug = "SocialLookupEmail"

    class RequestModel(BaseModel):
        email_address: str

        input_email_body: str | None

        url1: str | None
        url2: str | None
        company: str | None
        article_title: str | None
        domain: str | None
        key_words: str | None

        sampling_temperature: float | None
        max_tokens: int | None

    class ResponseModel(BaseModel):
        person_data: dict
        final_prompt: str
        output_email_body: str

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
        st.slider(
            """
            ##### Model Creativity 

            *(Sampling Temperature)*

            Higher values allow the model to take more risks.
            Try 0.9 for more creative applications, 
            and 0 for ones with a well-defined answer. 
            """,
            key="sampling_temperature",
            min_value=0.0,
            max_value=1.0,
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
            st.text_input(
                """
                ### Email Address
                Give us an email address and we'll try to get determine the profile data associated with it
                """,
                key="email_address",
                placeholder="john@appleseed.com",
            )
            st.caption(
                "By providing an email address, you agree to Gooey.AI's [Privacy Policy](https://gooey.ai/privacy)"
            )

            st.text_area(
                """
                ### Email Body
                """,
                key="input_email_body",
                height=200,
            )

            st.text_input("URL 1", key="url1")
            st.text_input("URL 2", key="url2")
            st.text_input("Company", key="company")
            st.text_input("Article Title", key="article_title")
            st.text_input("Domain", key="domain")
            st.text_input("Key Words", key="key_words")

            submitted = st.form_submit_button("🏃‍ Submit")

        if submitted:
            text_prompt = st.session_state.get("input_email_body")
            email_address = st.session_state.get("email_address")
            if not (text_prompt and email_address):
                st.error("Please provide a Prompt and an Email Address", icon="⚠️")
                return False

            if not re.fullmatch(email_regex, email_address):
                st.error("Please provide a valid Email Address", icon="⚠️")
                return False

        return submitted

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: SocialLookupEmailPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Fetching profile data..."

        person = get_profile_for_email(request.email_address)
        if not person:
            raise ValueError("Could not find person")
        state["person_data"] = person

        state["final_prompt"] = daras_ai_format_str(
            format_str=request.input_email_body,
            variables=self._input_variables(state),
        )

        yield "Running GPT-3..."

        state["output_email_body"] = run_language_model(
            api_provider="openai",
            engine="text-davinci-003",
            quality=1,
            num_outputs=1,
            temperature=request.sampling_temperature,
            prompt=state["final_prompt"],
            max_tokens=request.max_tokens,
            stop=None,
        )[0]

    def _input_variables(self, state: dict):
        return {
            "person": state.get("person_data"),
            "email_address": state.get("email_address"),
            "url1": state.get("url1"),
            "url2": state.get("url2"),
            "company": state.get("company"),
            "article_title": state.get("article_title"),
            "domain": state.get("domain"),
            "key_words": state.get("key_words"),
        }

    def render_output(self):
        st.text_area(
            """
            ### Email Body Output 
            """,
            disabled=True,
            value=st.session_state.get("output_email_body", ""),
            height=200,
        )

        with st.expander("Steps", expanded=True):
            person_data = st.session_state.get("person_data")
            if person_data:
                st.write("**Input Variables**")
                st.json(
                    self._input_variables(st.session_state),
                    expanded=False,
                )
            else:
                st.empty()

            final_prompt = st.session_state.get("final_prompt")
            if final_prompt:
                st.text_area(
                    "Final Prompt",
                    disabled=True,
                    value=final_prompt,
                    height=200,
                )
            else:
                st.empty()

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        st.write("**Email Address**")
        st.write(state.get("email_address", ""))
        st.write("**Email Body Output**")
        st.write(state.get("output_email_body", ""))


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

    person = r.json().get("person")
    if not person:
        return

    return person


if __name__ == "__main__":
    SocialLookupEmailPage().render()
