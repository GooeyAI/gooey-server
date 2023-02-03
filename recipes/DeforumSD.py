import datetime
import math
import typing
import uuid

import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import storage_blob_for
from daras_ai_v2.base import BasePage
from daras_ai_v2.gpu_server import GpuEndpoints


class _AnimationPrompt(typing.TypedDict):
    frame: str
    prompt: str


AnimationPrompts = list[_AnimationPrompt]


def input_prompt_to_animation_prompts(input_prompt: str):
    animation_prompts = []
    for fp in input_prompt.split("|"):
        split = fp.split(":")
        if len(split) == 2:
            frame = int(split[0])
            prompt = split[1].strip()
        else:
            frame = 0
            prompt = fp
        animation_prompts.append({"frame": frame, "prompt": prompt})
    return animation_prompts


def animation_prompts_to_st_list(animation_prompts: AnimationPrompts):
    return [
        {"frame": fp["frame"], "prompt": fp["prompt"], "key": str(uuid.uuid1())}
        for fp in animation_prompts
    ]


def st_list_to_animation_prompt(prompt_st_list) -> AnimationPrompts:
    return [{"frame": fp["frame"], "prompt": fp["prompt"]} for fp in prompt_st_list]


def animation_prompts_editor(
    animation_prompts_key: str = "animation_prompts",
    input_prompt_key: str = "input_prompt",
):
    st_list_key = f"__{animation_prompts_key}_st_list"
    if st_list_key in st.session_state:
        prompt_st_list = st.session_state[st_list_key]
    else:
        animation_prompts = st.session_state.get(
            animation_prompts_key
        ) or input_prompt_to_animation_prompts(
            st.session_state.get(input_prompt_key, "0:")
        )
        prompt_st_list = animation_prompts_to_st_list(animation_prompts)
        st.session_state[st_list_key] = prompt_st_list

    st.write("#### 💃 Animation Prompts")
    col_spec = [1, 4]
    col1, col2 = st.columns(col_spec)
    with col1:
        st.write("##### 🔢 Frame")
    with col2:
        st.write("##### 👩‍💻 Prompt")

    updated_st_list = []
    for idx, fp in enumerate(prompt_st_list):
        fp_key = fp["key"]
        frame_key = f"__{st_list_key}_frame_{fp_key}"
        prompt_key = f"__{st_list_key}_prompt_{fp_key}"
        if frame_key not in st.session_state:
            st.session_state[frame_key] = fp["frame"]
        if prompt_key not in st.session_state:
            st.session_state[prompt_key] = fp["prompt"]

        col1, col2 = st.columns(col_spec)
        with col1:
            if st.button("🗑️", help=f"remove frame {idx}"):
                prompt_st_list.pop(idx)
                st.experimental_rerun()
            st.number_input(
                label="frame",
                label_visibility="collapsed",
                key=frame_key,
                min_value=0,
                step=1,
            )
        with col2:
            st.text_area(
                label="prompt",
                label_visibility="collapsed",
                key=prompt_key,
                height=100,
            )

        updated_st_list.append(
            {
                "frame": st.session_state.get(frame_key),
                "prompt": st.session_state.get(prompt_key),
                "key": fp_key,
            }
        )

    prompt_st_list.clear()
    prompt_st_list.extend(updated_st_list)

    if st.button("➕ Add a Prompt"):
        max_frames = st.session_state.get("max_frames", 100)
        next_frame = max(fp["frame"] for fp in prompt_st_list)
        next_frame += max(min(max_frames - next_frame, 10), 1)

        if next_frame > max_frames:
            st.error("Please increase Frame Count")
        else:
            prompt_st_list.append(
                {
                    "frame": next_frame,
                    "prompt": "",
                    "key": str(uuid.uuid1()),
                }
            )
            st.experimental_rerun()

    st.session_state[animation_prompts_key] = st_list_to_animation_prompt(
        prompt_st_list
    )


class DeforumSDPage(BasePage):
    title = "AI Animation Generator"
    slug_versions = ["DeforumSD", "animation-generator"]

    sane_defaults = dict(
        zoom="0: (1.004)",
        translation_x="0:(10*sin(2*3.14*t/10))",
        translation_y="0:(0)",
        rotation_3d_x="0:(0)",
        rotation_3d_y="0:(0)",
        rotation_3d_z="0:(0)",
        fps=12,
        seed=42,
    )

    class RequestModel(BaseModel):
        # input_prompt: str
        animation_prompts: AnimationPrompts
        max_frames: int | None

        zoom: str
        translation_x: str | None
        translation_y: str | None
        rotation_3d_x: str
        rotation_3d_y: str
        rotation_3d_z: str
        fps: int

        seed: int

    class ResponseModel(BaseModel):
        output_video: str

    def render_form_v2(self):
        animation_prompts_editor()

        col1, col2 = st.columns(2)
        with col1:
            st.number_input(
                """
#### Frame Count
Number of animation frames.
                """,
                min_value=10,
                max_value=1000,
                step=10,
                key="max_frames",
            )

    def additional_notes(self) -> str | None:
        return """
*Cost ~= 0.25 credits per frame* \\
*Run Time ~= 5 seconds per frame*
        """

    def get_price(self) -> int:
        return math.ceil(st.session_state.get("max_frames", 100) * 0.25)

    def validate_form_v2(self):
        prompt_list = st.session_state.get("animation_prompts")
        assert prompt_list, "Please provide animation prompts"

        max_frames = st.session_state["max_frames"]
        assert (
            max(fp["frame"] for fp in prompt_list) <= max_frames
        ), "Please make sure that Frame Count matches the Animation Prompts"

    def render_settings(self):

        col1, col2 = st.columns(2)
        with col1:
            animation_mode = st.selectbox(
                "Animation Mode", key="animation_mode", options=["2D", "3D"]
            )

        st.text_input(
            """
###### Zoom
How should the camera zoom in or out? Scales the canvas size, multiplicatively. 1 is static, with numbers greater than 1 moving forwards and numbers less than 1 moving backwards. E.g. use `0: (1.004)` to zoom in moderately, starting at frame 0 and continuing until the end.
            """,
            key="zoom",
        )
        st.text_input(
            """
###### Horiztonal Pan
How should the camera pan horizontally? This parameter uses positive values to move right and negative values to move left.
            """,
            key="translation_x",
        )
        st.text_input(
            """
###### Vertical Pan
How should the camera pan vertically? This parameter uses positive values to move up and negative values to move down.
            """,
            key="translation_y",
        )
        if animation_mode == "3D":
            st.text_input(
                """
###### Camera Rotation
Rolls the camera clockwise or counterclockwise in degrees per frame. This parameter uses positive values to roll counterclockwise and negative values to roll clockwise. E.g. use `0:(-1), 20:(0)` to roll the camera 1 degree clockwise for the first 20 frames.
                """,
                key="rotation_3d_z",
            )
            st.text_input(
                """
###### Rotate Up/Down 
Tilts the camera up or down in degrees per frame. This parameter uses positive values to tilt up and negative values to tilt down.
                """,
                key="rotation_3d_y",
            )
            st.text_input(
                """
###### Rotate Left/Right 
Pans the canvas left or right in degrees per frame. This parameter uses positive values to pan right and negative values to pan left.
                """,
                key="rotation_3d_x",
            )
        st.slider(
            """
###### FPS
Choose fps for the video.
            """,
            min_value=10,
            max_value=60,
            step=1,
        )

        st.selectbox(
            """
###### Sampler
What Stable Diffusion sampler should be used.
            """,
            key="sampler",
            options=[
                "euler_ancestral",
                "klms",
                "dpm2",
                "dpm2_ancestral",
                "heun",
                "euler",
                "plms",
                "ddim",
                "dpm_fast",
                "dpm_adaptive",
                "dpmpp_2s_a",
                "dpmpp_2m",
            ],
        )

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
            st.markdown("```" + state.get("input_prompt").replace("\n", "") + "```")
            st.video(output_video)
        else:
            st.empty()

    def run(self, state: dict):
        request: DeforumSDPage.RequestModel = self.RequestModel.parse_obj(state)
        yield

        blob = storage_blob_for(f"gooey.ai animation {request.animation_prompts}.mp4")

        r = requests.post(
            GpuEndpoints.sd_multi + f"/deforum/",
            json={
                "pipeline": dict(
                    model_id="Protogen_V2.2.ckpt",
                    seed=request.seed,
                    upload_urls=[
                        blob.generate_signed_url(
                            version="v4",
                            # This URL is valid for 15 minutes
                            expiration=datetime.timedelta(minutes=60),
                            # Allow PUT requests using this URL.
                            method="PUT",
                            content_type="video/mp4",
                        )
                    ],
                ),
                "inputs": dict(
                    animation_mode="3D",
                    animation_prompts={
                        fp["frame"]: fp["prompt"] for fp in request.animation_prompts
                    },
                    max_frames=request.max_frames,
                    zoom=request.zoom,
                    translation_x=request.translation_x,
                    translation_y=request.translation_y,
                    rotation_3d_x=request.rotation_3d_x,
                    rotation_3d_y=request.rotation_3d_y,
                    rotation_3d_z=request.rotation_3d_z,
                    fps=request.fps,
                ),
            },
        )
        r.raise_for_status()

        state["output_video"] = blob.public_url


if __name__ == "__main__":
    DeforumSDPage().render()
