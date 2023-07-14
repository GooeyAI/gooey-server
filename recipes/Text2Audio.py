import datetime
import typing
from enum import Enum

import requests
import gooey_ui as st
from pydantic import BaseModel

from daras_ai.image_input import storage_blob_for
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.gpu_server import GpuEndpoints
from daras_ai_v2.img_model_settings_widgets import (
    negative_prompt_setting,
    guidance_scale_setting,
    num_outputs_setting,
)


class Text2AudioModels(Enum):
    audio_ldm = "AudioLDM (CVSSP)"


text2audio_model_ids = {
    Text2AudioModels.audio_ldm: "cvssp/audioldm",
}


class Text2AudioPage(BasePage):
    title = "Text guided audio generator"
    slug_versions = ["text2audio"]

    sane_defaults = dict(
        seed=42,
    )

    class RequestModel(BaseModel):
        text_prompt: str
        negative_prompt: str | None

        duration_sec: float | None

        num_outputs: int | None
        quality: int | None

        guidance_scale: float | None
        seed: int | None
        sd_2_upscaling: bool | None

        selected_models: list[
            typing.Literal[tuple(e.name for e in Text2AudioModels)]
        ] | None

    class ResponseModel(BaseModel):
        output_audios: dict[
            typing.Literal[tuple(e.name for e in Text2AudioModels)], list[str]
        ]

    def render_form_v2(self):
        st.text_area(
            """
            ### 👩‍💻 Prompt
            Describe the audio that you'd like to generate.
            """,
            key="text_prompt",
            placeholder="Iron man",
        )

        st.write("#### 🧨 Audio Model")
        enum_multiselect(
            Text2AudioModels,
            key="selected_models",
        )

    def validate_form_v2(self):
        assert st.session_state["text_prompt"], "Please provide a prompt"
        assert st.session_state["selected_models"], "Please select at least one model"

    def render_settings(self):
        st.slider(
            label="""
            ##### ⏱️ Audio Duration (sec)
            """,
            key="duration_sec",
            min_value=1,
            max_value=20,
            step=1,
        )
        negative_prompt_setting()
        num_outputs_setting()
        guidance_scale_setting()

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: Text2AudioPage.RequestModel = self.RequestModel.parse_obj(state)

        state["output_audios"] = output_audios = {}

        for selected_model in request.selected_models:
            yield f"Running {Text2AudioModels[selected_model].value}..."

            blobs = [
                storage_blob_for(f"gooey.ai - {request.text_prompt} ({i + 1}).wav")
                for i in range(request.num_outputs)
            ]
            r = requests.post(
                str(GpuEndpoints.audio_ldm),
                json={
                    "pipeline": {
                        "model_id": "cvssp/audioldm",
                        "upload_urls": [
                            blob.generate_signed_url(
                                version="v4",
                                # This URL is valid for 15 minutes
                                expiration=datetime.timedelta(minutes=30),
                                # Allow PUT requests using this URL.
                                method="PUT",
                                content_type="audio/wav",
                            )
                            for blob in blobs
                        ],
                        "seed": request.seed,
                    },
                    "inputs": {
                        "prompt": [request.text_prompt],
                        "negative_prompt": [request.negative_prompt]
                        if request.negative_prompt
                        else None,
                        "num_waveforms_per_prompt": request.num_outputs,
                        "num_inference_steps": request.quality,
                        "guidance_scale": request.guidance_scale,
                        "audio_length_in_s": request.duration_sec,
                    },
                },
            )
            r.raise_for_status()
            output_audios[selected_model] = [blob.public_url for blob in blobs]

    def render_output(self):
        _render_output(st.session_state)

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("```properties\n" + state.get("text_prompt", "") + "\n```")
        with col2:
            _render_output(state)

    def preview_description(self, state: dict) -> str:
        return "Generate AI Music with text instruction prompts. AudiLDM is capable of generating realistic audio samples by process any text input. Learn more [here](https://huggingface.co/cvssp/audioldm-m-full)."

def _render_output(state):
    selected_models = state.get("selected_models", [])
    for key in selected_models:
        output: dict = state.get("output_audios", {}).get(key, [])
        for audio in output:
            st.audio(audio, caption=Text2AudioModels[key].value)
