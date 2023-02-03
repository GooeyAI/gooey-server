import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.gpu_server import call_gpu_server_b64, GpuEndpoints

from recipes import (
    VideoBots,
    LipsyncTTS,
    CompareText2Img,
    FaceInpainting,
)

DEFAULT_ANIMATION_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/meta%20tags%20-%20animation.jpg"


class DeforumSDPage(BasePage):
    title = "AI Animation Generator"
    slug_versions = ["DeforumSD", "animation-generator"]

    class RequestModel(BaseModel):
        input_prompt: str
        max_frames: int | None

    class ResponseModel(BaseModel):
        output_video: str

    def related_workflows(self) -> list:
        return [
            VideoBots.VideoBotsPage,
            LipsyncTTS.LipsyncTTSPage,
            CompareText2Img.CompareText2ImgPage,
            FaceInpainting.FaceInpaintingPage,
        ]

    def render_form(self) -> bool:
        with st.form("my_form"):
            st.text_area(
                """
                ### Prompt
                """,
                key="input_prompt",
                height=200,
            )

            st.slider(
                "Number of Frames", min_value=100, max_value=1000, key="max_frames"
            )

            submitted = st.form_submit_button("🏃‍ Submit")

        return submitted

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_ANIMATION_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Input your text (including keyframes!) and animate using Stable Diffusion's Deforum. Create AI generated animation for free and easier than CoLab notebooks. Inspired by deforum.art."

    def render_description(self):
        st.write(
            """
            This recipe takes any text and creates animation. 

            It's based off the Deforum notebook with lots of details at http://deforum.art. 
            """
        )

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
            # st.write(f"**Output Video** - {state.get('input_prompt')}")
            st.markdown("```" + state.get("input_prompt").replace("\n", "") + "```")
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
                "zoom": "0: (1.004)",
            },
        )[0]
        state["output_video"] = upload_file_from_bytes(
            f"gooey.ai text to animation - {request.input_prompt}.mp4", out_video_bytes
        )


if __name__ == "__main__":
    DeforumSDPage().render()
