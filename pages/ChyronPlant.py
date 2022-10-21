from copy import deepcopy

import openai
import streamlit as st
from decouple import config
from pydantic import BaseModel

from daras_ai_v2.base import (
    logo,
    get_saved_state,
    run_as_api_tab,
    save_button,
)

DOC_NAME = "ChyronPlant"
API_URL = "/v1/ChyronPlant/run"


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


def main():
    logo()

    if not st.session_state:
        st.session_state.update(deepcopy(get_saved_state(DOC_NAME)))

    save_button(DOC_NAME)

    tab1, tab2, tab3 = st.tabs(["🏃‍♀️ Run", "⚙️ Settings", "🚀 Run as API"])

    with tab1:
        run_tab()

    with tab2:
        edit_tab()

    with tab3:
        run_as_api_tab(API_URL, RequestModel)


def run_tab():
    st.write(
        """
        # Chyron Plant Bot
        """
    )

    with st.form("my_form"):
        st.write(
            """
            ### Input Midi notes
            """
        )
        st.text_input(
            "",
            label_visibility="collapsed",
            key="midi_notes",
        )

        submitted = st.form_submit_button("🚀 Submit")

    gen = None
    if submitted:
        gen = run(st.session_state)

    st.write(
        """
        **MIDI translation**
        """
    )
    if gen:
        with st.spinner():
            next(gen)
    st.text_area(
        "",
        label_visibility="collapsed",
        key="midi_translation",
        disabled=True,
    )

    st.write(
        """
        ### Chyron Output
        """
    )
    if gen:
        with st.spinner():
            next(gen)
    st.text_area(
        "",
        label_visibility="collapsed",
        key="chyron_output",
        disabled=True,
        height=300,
    )


def edit_tab():
    st.write(
        """
        ### Midi Notes -> English GPT script
        """
    )
    st.text_area(
        "",
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
        "",
        label_visibility="collapsed",
        key="chyron_prompt",
        height=500,
    )


def run(state: dict):
    openai.api_key = config("OPENAI_API_KEY")

    state["midi_translation"] = run_midi_notes(state)
    yield state

    state["chyron_output"] = run_chyron(state)
    yield state


def run_midi_notes(state: dict):
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


def run_chyron(state: dict):
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


if __name__ == "__main__":
    main()
