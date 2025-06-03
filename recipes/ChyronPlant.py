import gooey_gui as gui
from pydantic import BaseModel

from bots.models import Workflow
from daras_ai_v2.base import (
    BasePage,
)


class ChyronPlantPage(BasePage):
    title = "Chyron Plant Bot"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aeb83ee8-889e-11ee-93dc-02420a000143/Youtube%20transcripts%20GPT%20extractions.png.png"
    workflow = Workflow.CHYRON_PLANT
    slug_versions = ["ChyronPlant"]

    class RequestModel(BasePage.RequestModel):
        midi_notes: str

        midi_notes_prompt: str | None = None
        chyron_prompt: str | None = None

    class ResponseModel(BaseModel):
        midi_translation: str
        chyron_output: str

    def render_form_v2(self):
        gui.text_input(
            """
            ### Input Midi notes
            """,
            key="midi_notes",
        )

    def render_output(self):
        gui.text_area(
            """
            **MIDI translation**
            """,
            value=gui.session_state.get("midi_translation", ""),
            disabled=True,
        )

        gui.text_area(
            """
            ### Chyron Output
            """,
            disabled=True,
            value=gui.session_state.get("chyron_output", ""),
            height=300,
        )

    def render_settings(self):
        gui.text_area(
            """
            ### Midi Notes -> English GPT script
            """,
            key="midi_notes_prompt",
            height=500,
        )

        gui.text_area(
            """
            ### Chyron Plant Radbot script
            """,
            key="chyron_prompt",
            height=500,
        )

    def run(self, state: dict):
        yield "Translating MIDI..."

        state["midi_translation"] = self.run_midi_notes(state)

        yield "Chyron is thinking..."

        state["chyron_output"] = self.run_chyron(state)

    def run_midi_notes(self, state: dict):
        from openai import OpenAI

        prompt = state.get("midi_notes_prompt", "").strip()
        prompt += "\nMIDI: " + state.get("midi_notes", "") + "\nEnglish:"

        client = OpenAI()
        r = client.completions.create(
            model="text-davinci-002",
            max_tokens=250,
            prompt=prompt,
            stop=["English:", "MIDI:", "\n"],
            best_of=1,
            n=1,
        )
        # choose the first completion that isn't empty
        for choice in r.choices:
            text = choice.text.strip()
            if text:
                return text
        return ""

    def run_chyron(self, state: dict):
        from openai import OpenAI

        prompt = state.get("chyron_prompt", "").strip()
        prompt += "\nUser: " + state.get("midi_translation", "").strip() + "\nChyron:"

        client = OpenAI()
        r = client.completions.create(
            model="text-davinci-002",
            max_tokens=250,
            prompt=prompt,
            stop=["\nChyron:", "\nUser:"],
            best_of=1,
            n=1,
        )
        # choose the first completion that isn't empty
        for choice in r.choices:
            text = choice.text.strip()
            if text:
                return text
        return ""

    def render_run_preview_output(self, state):
        col1, col2 = gui.columns(2)
        with col1:
            gui.write(state.get("midi_translation", ""))
        with col2:
            gui.write(state.get("chyron_output", ""))
