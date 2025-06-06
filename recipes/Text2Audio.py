import typing
from enum import Enum

from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_multiselect
from daras_ai_v2.gpu_server import call_celery_task_outfile
from daras_ai_v2.img_model_settings_widgets import (
    negative_prompt_setting,
    guidance_scale_setting,
    num_outputs_setting,
)
from daras_ai_v2.pydantic_validation import HttpUrlStr


class Text2AudioModels(Enum):
    audio_ldm = "AudioLDM (CVSSP)"


text2audio_model_ids = {
    Text2AudioModels.audio_ldm: "cvssp/audioldm",
}


class Text2AudioPage(BasePage):
    title = "Text guided audio generator"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a4481d58-88d9-11ee-aa86-02420a000165/Text%20guided%20audio%20generator.png.png"
    workflow = Workflow.TEXT_2_AUDIO
    slug_versions = ["text2audio"]

    sane_defaults = dict(
        seed=42,
    )

    class RequestModel(BasePage.RequestModel):
        text_prompt: str
        negative_prompt: str | None = None

        duration_sec: float | None = None

        num_outputs: int | None = None
        quality: int | None = None

        guidance_scale: float | None = None
        seed: int | None = None
        sd_2_upscaling: bool | None = None

        selected_models: (
            list[typing.Literal[tuple(e.name for e in Text2AudioModels)]] | None
        ) = None

    class ResponseModel(BaseModel):
        output_audios: dict[
            typing.Literal[tuple(e.name for e in Text2AudioModels)],
            list[HttpUrlStr],
        ]

    def render_form_v2(self):
        gui.text_area(
            """
            #### 👩‍💻 Prompt
            Describe the audio that you'd like to generate.
            """,
            key="text_prompt",
            placeholder="Iron man",
        )

        gui.write("#### 🧨 Audio Model")
        enum_multiselect(
            Text2AudioModels,
            key="selected_models",
        )

    def validate_form_v2(self):
        assert gui.session_state["text_prompt"], "Please provide a prompt"
        assert gui.session_state["selected_models"], "Please select at least one model"

    def render_settings(self):
        gui.slider(
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
        request: Text2AudioPage.RequestModel = self.RequestModel.model_validate(state)

        state["output_audios"] = output_audios = {}

        for selected_model in request.selected_models:
            model = Text2AudioModels[selected_model]
            model_id = text2audio_model_ids[model]

            yield f"Running {model.value}..."

            output_audios[selected_model] = call_celery_task_outfile(
                "audio_ldm",
                pipeline=dict(
                    model_id=model_id,
                    seed=request.seed,
                ),
                inputs=dict(
                    prompt=[request.text_prompt],
                    negative_prompt=(
                        [request.negative_prompt] if request.negative_prompt else None
                    ),
                    num_waveforms_per_prompt=request.num_outputs,
                    num_inference_steps=request.quality,
                    guidance_scale=request.guidance_scale,
                    audio_length_in_s=request.duration_sec,
                ),
                filename=f"gooey.ai - {request.text_prompt}.wav",
                content_type="audio/wav",
                num_outputs=request.num_outputs,
            )

    def render_output(self):
        _render_output(gui.session_state)

    def render_run_preview_output(self, state: dict):
        col1, col2 = gui.columns(2)
        with col1:
            gui.markdown("```properties\n" + state.get("text_prompt", "") + "\n```")
        with col2:
            _render_output(state)


def _render_output(state):
    selected_models = state.get("selected_models", [])
    for key in selected_models:
        output: dict = state.get("output_audios", {}).get(key, [])
        for audio in output:
            gui.audio(
                audio, caption=Text2AudioModels[key].value, show_download_button=True
            )
