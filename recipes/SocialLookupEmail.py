import re
import typing

import requests
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai.text_format import daras_ai_format_str
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.language_model import run_language_model, LargeLanguageModels
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.redis_cache import redis_cache_decorator

email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
DEFAULT_SOCIAL_LOOKUP_EMAIL_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/6729ea44-9457-11ee-bd77-02420a0001ce/Profile%20look%20up%20gpt%20email.jpg.png"


class SocialLookupEmailPage(BasePage):
    title = "Profile Lookup + GPT3 for AI-Personalized Emails"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/5fbd475a-88d7-11ee-aac9-02420a00016b/personalized%20email.png.png"
    workflow = Workflow.SOCIAL_LOOKUP_EMAIL
    slug_versions = ["SocialLookupEmail", "email-writer-with-profile-lookup"]

    sane_defaults = {
        "selected_model": LargeLanguageModels.gpt_4.name,
    }

    class RequestModel(BaseModel):
        email_address: str

        input_email_body: str | None

        url1: str | None
        url2: str | None
        company: str | None
        article_title: str | None
        domain: str | None
        key_words: str | None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )
        sampling_temperature: float | None
        max_tokens: int | None

    class ResponseModel(BaseModel):
        person_data: dict
        final_prompt: str
        output_email_body: str

    def preview_description(self, state: dict) -> str:
        return "Look up any email's public social profile (from LinkedIn, Facebook, the web, etc) and then use the profile's name, employment history, city, etc in your GPT3-powered AI mail merge to create personalized emails that get through spam filters."

    def related_workflows(self) -> list:
        from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.VideoBots import VideoBotsPage

        from recipes.GoogleGPT import GoogleGPTPage

        return [
            GoogleGPTPage,
            SEOSummaryPage,
            VideoBotsPage,
            EmailFaceInpaintingPage,
        ]

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_SOCIAL_LOOKUP_EMAIL_META_IMG

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

    def render_usage_guide(self):
        youtube_video("lVWQbS_rFaM")

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

    def render_form_v2(self):
        st.text_input(
            """
            #### Email Address
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
            #### Email Body
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

    def validate_form_v2(self):
        text_prompt = st.session_state.get("input_email_body")
        email_address = st.session_state.get("email_address")

        assert (
            text_prompt and email_address
        ), "Please provide a Prompt and an Email Address"

        assert re.fullmatch(
            email_regex, email_address
        ), "Please provide a valid Email Address"

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
            model=request.selected_model,
            quality=1,
            num_outputs=1,
            temperature=request.sampling_temperature,
            prompt=state["final_prompt"],
            max_tokens=request.max_tokens,
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
            #### Email Body Output 
            """,
            disabled=True,
            value=st.session_state.get("output_email_body", ""),
            height=200,
        )

    def render_steps(self):
        person_data = st.session_state.get("person_data")
        if person_data:
            st.write("**Input Variables**")
            st.json(
                self._input_variables(st.session_state),
                expanded=False,
            )
        else:
            st.div()

        final_prompt = st.session_state.get("final_prompt")
        if final_prompt:
            st.text_area(
                "Final Prompt",
                disabled=True,
                value=final_prompt,
                height=200,
            )
        else:
            st.div()

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        st.write("**Email Address**")
        st.write(state.get("email_address", ""))
        st.write("**Email Body Output**")
        st.write(state.get("output_email_body", ""))


@redis_cache_decorator
def get_profile_for_email(email_address) -> dict | None:
    r = requests.post(
        "https://api.apollo.io/v1/people/match",
        json={"api_key": settings.APOLLO_API_KEY, "email": email_address},
    )
    raise_for_status(r)

    person = r.json().get("person")
    if not person:
        return

    return person
