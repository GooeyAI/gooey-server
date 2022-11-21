import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints


class DeforumSDPage(BasePage):
    title = "Text to Animation"
    slug = "DeforumSD"

    class RequestModel(BaseModel):
        input_prompt: str
        max_frames: int | None

    class ResponseModel(BaseModel):
        output_video: str

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.write(
                """
                ### Prompt
                """
            )
            st.text_area(
                "input_prompt",
                label_visibility="collapsed",
                key="input_prompt",
                height=200,
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        return submitted

    def render_settings(self):
        st.slider("# of Frames", min_value=100, max_value=1000, key="max_frames")

    def render_output(self):
        output_video = st.session_state.get("output_video")
        if output_video:
            st.write("Output Video")
            st.video(output_video)
        else:
            st.empty()

    def render_example(self, state: dict):
        output_video = state.get("output_video")
        if output_video:
            st.write(f"**Output Video** - {state.get('input_prompt')}")
            st.video(output_video)
        else:
            st.empty()

    def run(self, state: dict):
        request = self.RequestModel.parse_obj(state)
        yield
        out_video_bytes = call_gpu_server_b64(
            endpoint=GpuEndpoints.deforum_sd,
            input_data={
                "max_frames": request.max_frames,
                "animation_prompts": request.input_prompt,
            },
        )[0]
        state["output_video"] = upload_file_from_bytes(
            f"gooey.ai text to animation - {request.input_prompt}", out_video_bytes
        )


if __name__ == "__main__":
    DeforumSDPage().render()
