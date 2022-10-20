import json
import os
import shlex
from copy import deepcopy
from threading import Thread

import openai
import requests
import streamlit as st
from decouple import config
from furl import furl
from google.cloud import firestore
from pydantic import BaseModel

from daras_ai import settings


def main():
    from daras_ai.logo import logo

    logo()

    if not st.session_state:
        st.session_state.update(deepcopy(get_doc()))

    st.button(" 💾 Save", on_click=save_me)

    tab1, tab2, tab3 = st.tabs(["🏃‍♀️ Run", "⚙️ Settings", "🚀 Run as API"])

    with tab1:
        run_tab()

    with tab2:
        edit_tab()

    with tab3:
        run_as_api_tab()


class RequestModel(BaseModel):
    midi_notes: str

    class Config:
        schema_extra = {
            "example": {
                "midi_notes": "C#1 B6 A2 A1 A3 A2",
            }
        }


class ResponseModel(BaseModel):
    midi_translation: str
    chyron_output: str


API_URL = "/v1/ChyronPlant/run"


def run_as_api_tab():
    api_url = str(furl(settings.DARS_API_ROOT) / API_URL)

    params = RequestModel.parse_obj(st.session_state).dict()

    st.write("### CURL request")

    st.write(
        rf"""```
curl -X 'POST' \
  {shlex.quote(api_url)} \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d {shlex.quote(json.dumps(params, indent=2))}
```"""
    )

    if st.button("Call API 🚀"):
        with st.spinner("Waiting for API..."):
            r = requests.post(api_url, json=params)
            "### Response"
            r.raise_for_status()
            st.write(r.json())


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


def run_tab():
    st.write(
        """
        # Chyron Plant Bot
        """
    )

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

    submit = st.button("Submit")
    if submit:
        st.session_state.update(run(st.session_state, st.session_state))

    st.write(
        """
        **MIDI translation**
        """
    )
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
    st.text_area(
        "",
        label_visibility="collapsed",
        key="chyron_output",
        disabled=True,
        height=300,
    )


def run(settings: dict, params: dict) -> dict:
    openai.api_key = config("OPENAI_API_KEY")
    midi_translation = run_midi_notes(settings, params.get("midi_notes", ""))
    chyron_output = run_chyron(settings, midi_translation)
    return {
        "midi_translation": midi_translation,
        "chyron_output": chyron_output,
    }


def run_midi_notes(settings, midi_notes):
    prompt = settings.get("midi_notes_prompt", "")
    prompt += "\nMIDI: " + midi_notes + "\nEnglish:"

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


def run_chyron(settings, midi_translation):
    prompt = settings.get("chyron_prompt", "")
    prompt += "\nUser: " + midi_translation.strip() + "\nChyron:"

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


def save_me():
    Thread(target=_save_me, args=[deepcopy(st.session_state.to_dict())]).start()


def _save_me(updated_settings):
    db = firestore.Client()
    db_collection = db.collection("daras-ai-v2")
    doc_ref = db_collection.document("ChyronPlant")

    doc_ref.set(updated_settings)

    cached_settings = get_doc()
    cached_settings.clear()
    cached_settings.update(updated_settings)


@st.cache(allow_output_mutation=True)
def get_doc():
    db = firestore.Client()
    db_collection = db.collection("daras-ai-v2")
    doc_ref = db_collection.document("ChyronPlant")
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({})
        doc = doc_ref.get()
    return doc.to_dict()


NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
OCTAVES = list(range(11))
NOTES_IN_OCTAVE = len(NOTES)


def number_to_note(number: int) -> str:
    octave = number // NOTES_IN_OCTAVE
    assert octave in OCTAVES, "Incorrect octave"
    assert 0 <= number <= 127, "Incorrect note"
    note = NOTES[number % NOTES_IN_OCTAVE]
    return f"{note}{octave}"


if __name__ == "__main__":
    main()
