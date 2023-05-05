import openai
import gooey_ui as st
from decouple import config
from pydantic import BaseModel

from daras_ai_v2 import settings
from daras_ai_v2.base import (
    BasePage,
)


class ChyronPlantPage(BasePage):
    title = "Chyron Plant Bot"
    slug_versions = ["ChyronPlant"]

    class RequestModel(BaseModel):
        midi_notes: str

        midi_notes_prompt: str | None
        chyron_prompt: str | None

        class Config:
            schema_extra = {
                "example": {
                    "midi_notes": "C#1 B6 A2 A1 A3 A2",
                }
            }

    class ResponseModel(BaseModel):
        midi_translation: str
        chyron_output: str

    def render_form(self):
        with st.form("my_form"):
            st.text_input(
                """
                ### Input Midi notes
                """,
                key="midi_notes",
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        return submitted

    def render_output(self):
        st.text_area(
            """
            **MIDI translation**
            """,
            value=st.session_state.get("midi_translation", ""),
            disabled=True,
        )

        st.text_area(
            """
            ### Chyron Output
            """,
            disabled=True,
            value=st.session_state.get("chyron_output", ""),
            height=300,
        )

    def render_settings(self):
        st.text_area(
            """
            ### Midi Notes -> English GPT script
            """,
            key="midi_notes_prompt",
            height=500,
        )

        st.text_area(
            """
            ### Chyron Plant Radbot script
            """,
            key="chyron_prompt",
            height=500,
        )

    def run(self, state: dict):
        openai.api_key = settings.OPENAI_API_KEY

        yield "Translating MIDI..."

        state["midi_translation"] = self.run_midi_notes(state)

        yield "Chyron is thinking..."

        state["chyron_output"] = self.run_chyron(state)

    def run_midi_notes(self, state: dict):
        prompt = state.get("midi_notes_prompt", "").strip()
        prompt += "\nMIDI: " + state.get("midi_notes", "") + "\nEnglish:"

        r = openai.Completion.create(
            engine="text-davinci-002",
            max_tokens=250,
            prompt=prompt,
            stop=["English:", "MIDI:", "\n"],
            best_of=1,
            n=1,
        )
        # choose the first completion that isn't empty
        for choice in r["choices"]:
            text = choice["text"].strip()
            if text:
                return text
        return ""

    def run_chyron(self, state: dict):
        prompt = state.get("chyron_prompt", "").strip()
        prompt += "\nUser: " + state.get("midi_translation", "").strip() + "\nChyron:"

        r = openai.Completion.create(
            engine="text-davinci-002",
            max_tokens=250,
            prompt=prompt,
            stop=["\nChyron:", "\nUser:"],
            best_of=1,
            n=1,
        )
        # choose the first completion that isn't empty
        for choice in r["choices"]:
            text = choice["text"].strip()
            if text:
                return text
        return ""

    def render_example(self, state):
        col1, col2 = st.columns(2)
        with col1:
            st.write(state.get("midi_translation", ""))
        with col2:
            st.write(state.get("chyron_output", ""))


if __name__ == "__main__":
    ChyronPlantPage().render()
