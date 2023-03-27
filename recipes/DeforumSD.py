import datetime
import math
import typing
import uuid

import requests
import streamlit as st
from furl import furl
from pydantic import BaseModel

from daras_ai.image_input import storage_blob_for
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.gpu_server import GpuEndpoints
from daras_ai_v2.loom_video_widget import youtube_video


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
    st_list_key = f"{animation_prompts_key}/st_list"
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

    st.write("#### 👩‍💻 Animation Prompts")
    st.caption(
        """
        Describe the scenes or series of images that you want to generate into an animation. You can add as many prompts as you like. Mention the keyframe number for each prompt i.e. the transition point from the first prompt to the next. 
        View the ‘Details’ drop down menu to get started.
        """
    )
    updated_st_list = []
    for idx, fp in enumerate(prompt_st_list):
        fp_key = fp["key"]
        frame_key = f"{st_list_key}/frame/{fp_key}"
        prompt_key = f"{st_list_key}/prompt/{fp_key}"
        if frame_key not in st.session_state:
            st.session_state[frame_key] = fp["frame"]
        if prompt_key not in st.session_state:
            st.session_state[prompt_key] = fp["prompt"]

        col1, col2 = st.columns([4, 1])
        with col1:
            st.text_area(
                label="*Prompt*",
                key=prompt_key,
                height=100,
            )
        with col2:
            st.number_input(
                label="*Frame*",
                key=frame_key,
                min_value=0,
                step=1,
            )
            if st.button("🗑️", help=f"Remove Frame {idx + 1}"):
                prompt_st_list.pop(idx)
                st.experimental_rerun()

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
        if prompt_st_list:
            next_frame = get_last_frame(prompt_st_list)
            next_frame += max(min(max_frames - next_frame, 10), 1)
        else:
            next_frame = 0
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
    st.caption(
        """
        Pro-tip: To avoid abrupt endings on your animation, ensure that the last keyframe prompt is set for a higher number of keyframes/time than the previous transition rate. There should be an ample number of frames between the last frame and the total frame count of the animation. 
        """
    )


def get_last_frame(prompt_list: list) -> int:
    return max(fp["frame"] for fp in prompt_list)


DEFAULT_ANIMATION_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/cropped_animation_meta.gif"


class DeforumSDPage(BasePage):
    title = "AI Animation Generator"
    slug_versions = ["DeforumSD", "animation-generator"]

    sane_defaults = dict(
        zoom="0: (1.004)",
        animation_mode="2D",
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

        animation_mode: str | None
        zoom: str | None
        translation_x: str | None
        translation_y: str | None
        rotation_3d_x: str | None
        rotation_3d_y: str | None
        rotation_3d_z: str | None
        fps: int | None

        seed: int | None

    class ResponseModel(BaseModel):
        output_video: str

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.FaceInpainting import FaceInpaintingPage

        return [
            VideoBotsPage,
            LipsyncTTSPage,
            CompareText2ImgPage,
            FaceInpaintingPage,
        ]

    def render_form_v2(self):
        animation_prompts_editor()

        col1, col2 = st.columns(2)
        with col1:
            st.number_input(
                """
                #### Frame Count
                Choose the number of frames in your animation.
                """,
                min_value=10,
                max_value=1000,
                step=10,
                key="max_frames",
            )

    def additional_notes(self) -> str | None:
        return """
*Cost ≈ 0.25 credits per frame* \\
*Process Run Time ≈ 5 seconds per frame*
        """

    def get_price(self) -> int:
        return math.ceil(st.session_state.get("max_frames", 100) * 0.25)

    def validate_form_v2(self):
        prompt_list = st.session_state.get("animation_prompts")
        assert prompt_list, "Please provide animation prompts"

        max_frames = st.session_state["max_frames"]
        assert (
            get_last_frame(prompt_list) <= max_frames
        ), "Please make sure that Frame Count matches the Animation Prompts"

    def render_usage_guide(self):
        youtube_video("DwhUJ6O_6E8")

    def render_settings(self):
        col1, col2 = st.columns(2)
        with col1:
            animation_mode = st.selectbox(
                "Animation Mode", key="animation_mode", options=["2D", "3D"]
            )

        st.text_input(
            """
###### Zoom
How should the camera zoom in or out? This setting scales the canvas size, multiplicatively. 
1 is static, with numbers greater than 1 moving forward (or zooming in) and numbers less than 1 moving backwards (or zooming out). 
            """,
            key="zoom",
        )
        st.caption(
            """
            With 0 as the starting keyframe, the input of 0: (1.004) can be used to zoom in moderately, starting at frame 0 and continuing until the end. 
            """
        )
        st.text_input(
            """
###### Horizontal Pan
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
Gradually moves the camera on a focal axis. Roll the camera clockwise or counterclockwise in a specific degree per frame. This parameter uses positive values to roll counterclockwise and negative values to roll clockwise. E.g. use `0:(-1), 20:(0)` to roll the camera 1 degree clockwise for the first 20 frames.
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
###### FPS (Frames per second) 
Choose fps for the video.
            """,
            min_value=10,
            max_value=60,
            step=1,
            key="fps",
        )

    #         st.selectbox(
    #             """
    # ###### Sampler
    # What Stable Diffusion sampler should be used.
    #             """,
    #             key="sampler",
    #             options=[
    #                 "euler_ancestral",
    #                 "klms",
    #                 "dpm2",
    #                 "dpm2_ancestral",
    #                 "heun",
    #                 "euler",
    #                 "plms",
    #                 "ddim",
    #                 "dpm_fast",
    #                 "dpm_adaptive",
    #                 "dpmpp_2s_a",
    #                 "dpmpp_2m",
    #             ],
    #         )

    def fallback_preivew_image(self) -> str:
        return DEFAULT_ANIMATION_META_IMG

    def preview_description(self, state: dict) -> str:
        return "Inspired by deforum.art, create AI-generated Animation for free without complex CoLab notebooks. Input your text prompts with keyframe numbers and animate using Stable Diffusion's Deforum."

    def render_description(self):
        st.markdown(
            """
Animation Length: You can indicate how long you want your animation to be by increasing or decreasing your frame count. 

FPS: Every Animation is set at 12 frames per second by default. You can change this default frame rate/ frames per second (FPS) on the Settings menu. 

Prompts: Within your sequence you can input multiple text Prompts for your visuals. Each prompt can be defined for a specific keyframe number. 

##### What are keyframes? 

Keyframes define the transition points from one prompt to the next, or the start and end points of a prompted action set in between the total frame count or sequence. These keyframes or markers are necessary to establish smooth transitions or jump cuts, whatever you prefer.

Use the Camera Settings to generate animations with depth and other 3D parameters.  
            """
        )
        st.markdown(
            f"""
            ##### How can you construct the visual prompts?
            
            - What is the Medium of the stills in your animation? 
            eg. It is a painting, a sculpture, an old photograph, portrait, 3D render, etc.
            - What/Who are the Subject(s) or Main Object(s)?
            eg. A human, an animal, an identity like gender, race, or occupation like dancer, astronaut etc. 
            - What is the Style?
            eg. Is it Analogue photography, a watercolor, a line drawing, digital painting etc. 
            - What are the Details?
            eg. facial features or expressions, the space and landscape, lighting or the colours etc. 

            [Example]({furl(settings.APP_BASE_URL).add(path='animation-generator').add({"example_id": "czvtn7du"}).url})
            
            """
        )
        st.markdown(
            """
            Pro-tip:

            Changing Elements transition better from a visual prompt that is artefact or object heavy to another busy visual prompt. For example: Prompt 1: a busy street transitions to Prompt 2: a busy interior of a park. This transition will render interesting and beautiful imagery.

            `Transitions from a simpler or plain visual prompt to a more complex visual might be challenging to generate. For example: Prompt 1: a blue sky to Prompt 2: a crowded market. This is because there are fewer artefacts for the generator to transition.`

            This recipe takes any text and creates animation. It's based on the Deforum notebook with lots of details at http://deforum.art.

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
        input_prompt = state.get("input_prompt")
        if input_prompt:
            animation_prompts = input_prompt_to_animation_prompts(input_prompt)
        else:
            animation_prompts = state.get("animation_prompts", [])
        display = "\n\n".join(
            [f"[{fp['frame']}] {fp['prompt']}" for fp in animation_prompts]
        )
        st.markdown("```lua\n" + display + "\n```")

        st.video(state.get("output_video"))

    def run(self, state: dict):
        request: DeforumSDPage.RequestModel = self.RequestModel.parse_obj(state)
        yield

        blob = storage_blob_for(f"gooey.ai animation {request.animation_prompts}.mp4")

        r = requests.post(
            GpuEndpoints.defourm_sd,
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
                    animation_mode=request.animation_mode,
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
                    translation_z="0:(0)",
                    fps=request.fps,
                ),
            },
        )
        r.raise_for_status()

        state["output_video"] = blob.public_url


if __name__ == "__main__":
    DeforumSDPage().render()
