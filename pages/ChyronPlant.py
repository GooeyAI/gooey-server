import openai
import streamlit as st
from decouple import config
from pydantic import BaseModel

from daras_ai_v2.base import (
    DarsAiPage,
)


class ChyronPlantPage(DarsAiPage):
    doc_name = "ChyronPlant"
    endpoint = "/v1/ChyronPlant/run"

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

    def render_title(self):
        st.write(
            """
            # Chyron Plant Bot
            """
        )

    def render_form(self):
        with st.form("my_form"):
            st.write(
                """
                ### Input Midi notes
                """
            )
            st.text_input(
                "midi_notes",
                label_visibility="collapsed",
                key="midi_notes",
            )

            submitted = st.form_submit_button("🚀 Submit")

        return submitted

    def render_output(self):
        st.write(
            """
            **MIDI translation**
            """
        )
        st.text_area(
            "midi_translation",
            label_visibility="collapsed",
            value=st.session_state.get("midi_translation", ""),
            disabled=True,
        )

        st.write(
            """
            ### Chyron Output
            """
        )
        st.text_area(
            "chyron_output",
            label_visibility="collapsed",
            disabled=True,
            value=st.session_state.get("chyron_output", ""),
            height=300,
        )

    def render_settings(self):
        st.write(
            """
            ### Midi Notes -> English GPT script
            """
        )
        st.text_area(
            "midi_notes_prompt",
            label_visibility="collapsed",
            key="midi_notes_prompt",
            height=500,
        )

        st.write(
            """
            ### Chyron Plant Radbot script
            """
        )
        st.text_area(
            "chyron_prompt",
            label_visibility="collapsed",
            key="chyron_prompt",
            height=500,
        )

    def run(self, state: dict):
        openai.api_key = config("OPENAI_API_KEY")

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
