import random
import typing

import requests
import streamlit as st
from google.cloud import translate_v2
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.image_input import upload_st_file
from daras_ai_v2.asr import (
    AsrModels,
    google_translate_language_selector,
    asr_model_ids,
    run_asr,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    document_uploader,
)
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.face_restoration import map_parallel
from daras_ai_v2.gpu_server import GpuEndpoints


class AsrPage(BasePage):
    title = "Automatic Speech Recognition"
    slug_versions = ["asr"]

    sane_defaults = {}

    class RequestModel(BaseModel):
        documents: list[str] | None

        selected_model: typing.Literal[tuple(e.name for e in AsrModels)] | None

        google_translate_target: str | None

    class ResponseModel(BaseModel):
        output_text: list[str]

    def render_form_v2(self):
        document_uploader("##### Audio Files", type=("wav", "ogg", "mp3", "aac"))

        enum_selector(AsrModels, label="###### ASR Model", key="selected_model")

        google_translate_language_selector()

    def validate_form_v2(self):
        document_files: list[UploadedFile] | None = st.session_state.get(
            "__documents_files"
        )
        if document_files:
            uploaded = []
            for f in document_files:
                if f.name == "urls.txt":
                    uploaded.extend(f.getvalue().decode().splitlines())
                else:
                    uploaded.append(upload_st_file(f))
            st.session_state["documents"] = uploaded
        assert st.session_state.get("documents"), "Please provide at least 1 Document"

    def render_output(self):
        selected_model = AsrModels[st.session_state.get("selected_model")]
        if not selected_model:
            return
        output_text = st.session_state.get("output_text", [])
        for text in output_text:
            st.text_area(
                f"Transcription",
                help=f"output {random.random()}",
                value=text,
                disabled=True,
                height=300,
            )

    def run(self, state: dict):
        request: AsrPage.RequestModel = self.RequestModel.parse_obj(state)

        selected_model = AsrModels[request.selected_model]
        yield f"Running {selected_model.value}..."

        state["output_text"] = map_parallel(
            lambda audio: run_asr(
                audio,
                selected_model=request.selected_model,
                google_translate_target=request.google_translate_target,
            ),
            request.documents,
        )
