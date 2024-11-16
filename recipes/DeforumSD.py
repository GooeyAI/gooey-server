import typing
import uuid

from daras_ai_v2.pydantic_validation import FieldHttpUrl
from django.db.models import TextChoices
from pydantic import BaseModel
from typing_extensions import TypedDict

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.gpu_server import call_celery_task_outfile
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.safety_checker import safety_checker

DEFAULT_DEFORUMSD_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/7dc25196-93fe-11ee-9e3a-02420a0001ce/AI%20Animation%20generator.jpg.png"


class AnimationModels(TextChoices):
    protogen_2_2 = ("Protogen_V2.2.ckpt", "Protogen V2.2 (darkstorm2150)")
    epicdream = ("epicdream.safetensors", "epiCDream (epinikion)")


class _AnimationPrompt(TypedDict):
    frame: str
    prompt: str
    second: float


AnimationPrompts = list[_AnimationPrompt]

CREDITS_PER_FRAME = 1.5
MODEL_ESTIMATED_TIME_PER_FRAME = 2.4  # seconds


def input_prompt_to_animation_prompts(input_prompt: str):
    animation_prompts = []
    for fp in input_prompt.split("|"):
        split = fp.split(":")
        if len(split) == 3:
            frame = int(split[0])
            prompt = split[1].strip()
            second = float(split[2])
        else:
            frame = 0
            prompt = fp
            second = 0
        animation_prompts.append({"frame": frame, "prompt": prompt, "second": second})
    return animation_prompts


def animation_prompts_to_st_list(animation_prompts: AnimationPrompts):
    if "second" in animation_prompts[0]:
        return [
            {
                "frame": fp["frame"],
                "prompt": fp["prompt"],
                "second": fp["second"],
                "key": str(uuid.uuid1()),
            }
            for fp in animation_prompts
        ]
    else:
        return [
            {
                "frame": fp["frame"],
                "prompt": fp["prompt"],
                "second": frames_to_seconds(
                    int(fp["frame"]), gui.session_state.get("fps", 12)
                ),
                "key": str(uuid.uuid1()),
            }
            for fp in animation_prompts
        ]


def st_list_to_animation_prompt(prompt_st_list) -> AnimationPrompts:
    return [
        {"frame": fp["frame"], "prompt": prompt, "second": fp["second"]}
        for fp in prompt_st_list
        if (prompt := fp["prompt"].strip())
    ]


def animation_prompts_editor(
    animation_prompts_key: str = "animation_prompts",
    input_prompt_key: str = "input_prompt",
):
    st_list_key = f"{animation_prompts_key}/st_list"
    if st_list_key in gui.session_state:
        prompt_st_list = gui.session_state[st_list_key]
    else:
        animation_prompts = gui.session_state.get(
            animation_prompts_key
        ) or input_prompt_to_animation_prompts(
            gui.session_state.get(input_prompt_key, "0:")
        )
        prompt_st_list = animation_prompts_to_st_list(animation_prompts)
        gui.session_state[st_list_key] = prompt_st_list

    gui.write("#### 👩‍💻 Animation Prompts")
    gui.caption(
        """
        Describe the scenes or series of images that you want to generate into an animation. You can add as many prompts as you like. Mention the keyframe number for each prompt i.e. the transition point from the first prompt to the next.
        """
    )
    gui.write("#### Step 1: Draft & Refine Keyframes")
    updated_st_list = []
    col1, col2, col3 = gui.columns([2, 9, 2], responsive=False)
    max_seconds = gui.session_state.get("max_seconds", 10)
    with col1:
        gui.write("Second")
    with col2:
        gui.write("Prompt")
    with col3:
        gui.write("Camera")
    for idx, fp in enumerate(prompt_st_list):
        fp_key = fp["key"]
        frame_key = f"{st_list_key}/frame/{fp_key}"
        prompt_key = f"{st_list_key}/prompt/{fp_key}"
        second_key = f"{st_list_key}/seconds/{fp_key}"
        if second_key not in gui.session_state:
            gui.session_state[second_key] = fp["second"]
        gui.session_state[frame_key] = seconds_to_frames(
            gui.session_state[second_key], gui.session_state.get("fps", 12)
        )
        if prompt_key not in gui.session_state:
            gui.session_state[prompt_key] = fp["prompt"]

        col1, col2, col3 = gui.columns([2, 9, 2], responsive=False)
        fps = gui.session_state.get("fps", 12)
        max_seconds = gui.session_state.get("max_seconds", 10)
        start = fp["second"]
        end = (
            prompt_st_list[idx + 1]["second"]
            if idx + 1 < len(prompt_st_list)
            else max_seconds
        )
        with col1:
            gui.number_input(
                label="", key=second_key, min_value=0, step=0.1, style={"width": "56px"}
            )
            if idx != 0 and gui.button(
                "🗑️",
                help=f"Remove Frame {idx + 1}",
                type="tertiary",
                style={"float": "left;"},
            ):
                prompt_st_list.pop(idx)
                gui.rerun()
            if gui.button(
                '<i class="fa-regular fa-plus"></i>',
                help=f"Insert Frame after Frame {idx + 1}",
                type="tertiary",
                style={"float": "left;"},
            ):
                next_second = round((start + end) / 2, 2)
                if next_second > max_seconds:
                    gui.error("Please increase Frame Count")
                else:
                    prompt_st_list.insert(
                        idx + 1,
                        {
                            "frame": seconds_to_frames(next_second, fps),
                            "prompt": prompt_st_list[idx]["prompt"],
                            "second": next_second,
                            "key": str(uuid.uuid1()),
                        },
                    )
                    gui.rerun()

        with col2:
            gui.text_area(
                label="",
                key=prompt_key,
                height=100,
            )
        with col3:
            zoom_pan_modal = gui.use_confirm_dialog(
                key="modal-" + fp_key, close_on_confirm=False
            )
            zoom_dict = get_zoom_pan_dict(gui.session_state.get("zoom", {0: 1.004}))
            zoom_value = 0.0 if fp["frame"] not in zoom_dict else zoom_dict[fp["frame"]]
            hpan_dict = get_zoom_pan_dict(
                gui.session_state.get("translation_x", {0: 1.004})
            )
            hpan_value = 0.0 if fp["frame"] not in hpan_dict else hpan_dict[fp["frame"]]
            vpan_dict = get_zoom_pan_dict(
                gui.session_state.get("translation_y", {0: 1.004})
            )
            vpan_value = 0.0 if fp["frame"] not in vpan_dict else vpan_dict[fp["frame"]]
            zoom_pan_description = ""
            if zoom_value:
                zoom_pan_description = "Out: " if zoom_value > 1 else "In: "
                zoom_pan_description += f"{round(zoom_value, 3)}\n"
            if hpan_value:
                zoom_pan_description += "Right: " if hpan_value > 1 else "Left: "
                zoom_pan_description += f"{round(hpan_value, 3)}\n"
            if vpan_value:
                zoom_pan_description += "Up: " if vpan_value > 1 else "Down: "
                zoom_pan_description += f"{round(vpan_value, 3)}"
            if not zoom_pan_description:
                zoom_pan_description = '<i class="fa-solid fa-camera-movie"></i>'
            if gui.button(
                zoom_pan_description,
                key="button-" + fp_key,
                type="link",
            ):
                zoom_pan_modal.set_open(True)
            if zoom_pan_modal.is_open:
                with gui.confirm_dialog(
                    ref=zoom_pan_modal,
                    modal_title=f"### Zoom/Pan",
                    confirm_label="Save",
                    large=True,
                ):
                    gui.write(
                        f"#### Keyframe second {start} until {end}",
                    )
                    gui.caption(
                        f"Starting at second {start} and until second {end}, how do you want the camera to move? (Reasonable valuables would be ±0.005)"
                    )
                    zoom_pan_slider = gui.slider(
                        label="""
                        #### Zoom
                        """,
                        min_value=-1.5,
                        max_value=1.5,
                        step=0.001,
                        value=0,
                    )
                    hpan_slider = gui.slider(
                        label="""
                        #### Horizontal Pan
                        """,
                        min_value=-1.5,
                        max_value=1.5,
                        step=0.001,
                        value=0,
                    )
                    vpan_slider = gui.slider(
                        label="""
                        #### Vertical Pan
                        """,
                        min_value=-1.5,
                        max_value=1.5,
                        step=0.001,
                        value=0,
                    )
                    if zoom_pan_modal.pressed_confirm:
                        zoom_dict.update({fp["frame"]: 1 + zoom_pan_slider})
                        hpan_dict.update({fp["frame"]: hpan_slider})
                        vpan_dict.update({fp["frame"]: vpan_slider})
                        gui.session_state["zoom"] = get_zoom_pan_string(zoom_dict)
                        gui.session_state["translation_x"] = get_zoom_pan_string(
                            hpan_dict
                        )
                        gui.session_state["translation_y"] = get_zoom_pan_string(
                            vpan_dict
                        )
                        zoom_pan_modal.set_open(False)
                        gui.rerun()

        updated_st_list.append(
            {
                "frame": gui.session_state.get(frame_key),
                "prompt": gui.session_state.get(prompt_key),
                "second": gui.session_state.get(second_key),
                "key": fp_key,
            }
        )

    prompt_st_list.clear()
    prompt_st_list.extend(updated_st_list)

    gui.session_state[animation_prompts_key] = st_list_to_animation_prompt(
        prompt_st_list
    )


def get_last_frame(prompt_list: list) -> int:
    return max(fp["frame"] for fp in prompt_list)


def frames_to_seconds(frames: int, fps: int) -> float:
    return round(frames / int(fps), 2)


def seconds_to_frames(seconds: float, fps: int) -> int:
    return int(seconds * int(fps))


def get_zoom_pan_string(zoom_pan_string: dict[int, float]) -> str:
    return ", ".join([f"{frame}:({zoom})" for frame, zoom in zoom_pan_string.items()])


def get_zoom_pan_dict(zoom_pan_string: str) -> dict[int, float]:
    zoom_dict = {}
    pairs = zoom_pan_string.split(", ")
    for pair in pairs:
        frame, zoom = pair.split(":(")
        frame = int(frame.strip())
        zoom = float(zoom.strip().rstrip(")"))  # Remove the closing parenthesis
        zoom_dict[frame] = zoom
    return zoom_dict


DEFAULT_ANIMATION_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/assets/cropped_animation_meta.gif"


class DeforumSDPage(BasePage):
    title = "AI Animation Generator"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/media/users/kxmNIYAOJbfOURxHBKNCWeUSKiP2/dd88c110-88d6-11ee-9b4f-2b58bd50e819/animation.gif"
    workflow = Workflow.DEFORUM_SD
    slug_versions = ["DeforumSD", "animation-generator"]

    sane_defaults = dict(
        zoom="0: (1.004)",
        animation_mode="2D",
        translation_x="0:(0)",
        translation_y="0:(0)",
        rotation_3d_x="0:(0)",
        rotation_3d_y="0:(0)",
        rotation_3d_z="0:(0)",
        fps=12,
        seed=42,
        selected_model=AnimationModels.protogen_2_2.name,
    )

    class RequestModel(BasePage.RequestModel):
        # input_prompt: str
        animation_prompts: AnimationPrompts
        max_frames: int | None

        selected_model: typing.Literal[tuple(e.name for e in AnimationModels)] | None

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
        output_video: FieldHttpUrl

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_DEFORUMSD_META_IMG

    def related_workflows(self) -> list:
        from recipes.VideoBots import VideoBotsPage
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.QRCodeGenerator import QRCodeGeneratorPage

        return [
            QRCodeGeneratorPage,
            VideoBotsPage,
            LipsyncTTSPage,
            CompareText2ImgPage,
        ]

    def render_form_v2(self):
        animation_prompts_editor()

        col1, col2 = gui.columns(2)
        with col1:
            gui.number_input(
                label="",
                key="max_seconds",
                min_value=0,
                step=0.1,
                value=frames_to_seconds(
                    gui.session_state.get("max_frames", 100),
                    gui.session_state.get("fps", 12),
                ),
                style={"width": "56px"},
            )
            gui.session_state["max_frames"] = seconds_to_frames(
                gui.session_state.get("max_seconds", 10),
                gui.session_state.get("fps", 12),
            )
        with col2:
            gui.write("*End of Video*")

        gui.write("#### Step 2: Increase Animation Quality")
        gui.write(
            "Once you like your keyframes, increase your frames per second for high quality"
        )
        fps_options = [2, 10, 24]
        option_descriptions = ["Draft", "Stop-motion", "Film"]
        options = {
            str(fps): f"{label}: {fps} FPS"
            for fps, label in zip(fps_options, option_descriptions)
        }
        gui.radio(
            """###### FPS (Frames per second)""",
            options=options,
            key="fps",
        )

    def get_cost_note(self) -> str | None:
        return f"{gui.session_state.get('max_frames')} frames @ {CREDITS_PER_FRAME} Cr /frame"

    def additional_notes(self) -> str | None:
        return "Render Time ≈ 3s / frame"

    def get_raw_price(self, state: dict) -> float:
        max_frames = state.get("max_frames", 100) or 0
        return max_frames * CREDITS_PER_FRAME

    def validate_form_v2(self):
        prompt_list = gui.session_state.get("animation_prompts")
        assert prompt_list, "Please provide animation prompts"

        max_frames = gui.session_state["max_frames"]
        assert (
            get_last_frame(prompt_list) <= max_frames
        ), "Please make sure that Frame Count matches the Animation Prompts"

    def render_usage_guide(self):
        youtube_video("sUvica6UuQU")

    def render_settings(self):
        col1, col2 = gui.columns(2)
        with col1:
            enum_selector(
                AnimationModels,
                label="""
            Choose your preferred AI Animation Model
            """,
                key="selected_model",
                use_selectbox=True,
            )

            animation_mode = gui.selectbox(
                "Animation Mode", key="animation_mode", options=["2D", "3D"]
            )

        gui.text_input(
            """
###### Zoom
How should the camera zoom in or out? This setting scales the canvas size, multiplicatively.
1 is static, with numbers greater than 1 moving forward (or zooming in) and numbers less than 1 moving backwards (or zooming out).
            """,
            key="zoom",
        )
        gui.caption(
            """
            With 0 as the starting keyframe, the input of 0: (1.004) can be used to zoom in moderately, starting at frame 0 and continuing until the end.
            """
        )
        gui.text_input(
            """
###### Horizontal Pan
How should the camera pan horizontally? This parameter uses positive values to move right and negative values to move left.
            """,
            key="translation_x",
        )
        gui.text_input(
            """
###### Vertical Pan
How should the camera pan vertically? This parameter uses positive values to move up and negative values to move down.
            """,
            key="translation_y",
        )
        if animation_mode == "3D":
            gui.text_input(
                """
###### Roll Clockwise/Counterclockwise
Gradually moves the camera on a focal axis. Roll the camera clockwise or counterclockwise in a specific degree per frame. This parameter uses positive values to roll counterclockwise and negative values to roll clockwise. E.g. use `0:(-1), 20:(0)` to roll the camera 1 degree clockwise for the first 20 frames.
                """,
                key="rotation_3d_z",
            )
            gui.text_input(
                """
###### Pan Left/Right
Pans the canvas left or right in degrees per frame. This parameter uses positive values to pan right and negative values to pan left.
                """,
                key="rotation_3d_y",
            )
            gui.text_input(
                """
###### Tilt Up/Down
Tilts the camera up or down in degrees per frame. This parameter uses positive values to tilt up and negative values to tilt down.
                """,
                key="rotation_3d_x",
            )

    #         gui.selectbox(
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
        return "Create AI-generated Animation without relying on complex CoLab notebooks. Input your prompts + keyframes and bring your ideas to life using the animation capabilities of Gooey & Stable Diffusion's Deforum. For more help on how to use the tool visit https://www.help.gooey.ai/learn-animation"

    def render_description(self):
        gui.markdown(
            f"""
            - Every Submit will require approximately 3-5 minutes to render.

            - Animation is complex: Please watch the video and review our decks to help you.

            - Test your image prompts BEFORE adding lots of frames e.g. Tweak key frame images with just 10 frames between them AND then increase the FPS or frame count between them once you like the outputs. This will save you time and credits.

            - No lost work! All your animations or previously generated versions are in the History tab. If they don't appear here, it likely means they aren't done rendering yet.

            """
        )
        gui.markdown(
            """
            #### Resources:

            [Learn Animation](https://www.help.gooey.ai/learn-animation)

            [Gooey Guide to Prompting](https://docs.google.com/presentation/d/1RaoMP0l7FnBZovDAR42zVmrUND9W5DW6eWet-pi6kiE/edit?usp=sharing)

            Here’s a comprehensive style guide to assist you with different stylized animation prompts:

            [StableDiffusion CheatSheet](https://supagruen.github.io/StableDiffusion-CheatSheet/)

            """
        )
        gui.write("---")
        gui.markdown(
            """
            Animation Length: You can indicate how long you want your animation to be by increasing or decreasing your frame count.

            FPS: Every Animation is set at 12 frames per second by default. You can change this default frame rate/ frames per second (FPS) on the Settings menu.

            Prompts: Within your sequence you can input multiple text Prompts for your visuals. Each prompt can be defined for a specific keyframe number.

            ##### What are keyframes?

            Keyframes define the transition points from one prompt to the next, or the start and end points of a prompted action set in between the total frame count or sequence. These keyframes or markers are necessary to establish smooth transitions or jump cuts, whatever you prefer.

            Use the Camera Settings to generate animations with depth and other 3D parameters.
            """
        )
        gui.markdown(
            """
            Prompt Construction Tip:

            Changing Elements transition better from a visual prompt that is artefact or object heavy to another busy visual prompt. For example: Prompt 1: a busy street transitions to Prompt 2: a busy interior of a park. This transition will render interesting and beautiful imagery.

            `Transitions from a simpler or plain visual prompt to a more complex visual might be challenging to generate. For example: Prompt 1: a blue sky to Prompt 2: a crowded market. This is because there are fewer artefacts for the generator to transition.`

            This recipe takes any text and creates animation. It's based on the Deforum notebook with lots of details at http://deforum.art.

            """
        )

    def render_output(self):
        output_video = gui.session_state.get("output_video")
        if output_video:
            gui.write("#### Output Video")
            gui.video(output_video, autoplay=True, show_download_button=True)

    def estimate_run_duration(self):
        # in seconds
        return gui.session_state.get("max_frames", 100) * MODEL_ESTIMATED_TIME_PER_FRAME

    def render_example(self, state: dict):
        display = self.preview_input(state)
        gui.markdown("```lua\n" + display + "\n```")

        gui.video(state.get("output_video"), autoplay=True)

    @classmethod
    def preview_input(cls, state: dict) -> str:
        input_prompt = state.get("input_prompt")
        if input_prompt:
            animation_prompts = input_prompt_to_animation_prompts(input_prompt)
        else:
            animation_prompts = state.get("animation_prompts", [])
        display = "\n\n".join(
            [f"{fp['prompt']} [{fp['frame']}]" for fp in animation_prompts]
        )
        return display

    def run(self, state: dict):
        request: DeforumSDPage.RequestModel = self.RequestModel.parse_obj(state)
        yield

        if not self.request.user.disable_safety_checker:
            safety_checker(text=self.preview_input(state))

        try:
            state["output_video"] = call_celery_task_outfile(
                "deforum",
                pipeline=dict(
                    model_id=AnimationModels[request.selected_model].value,
                    seed=request.seed,
                ),
                inputs=dict(
                    animation_mode=request.animation_mode,
                    animation_prompts={
                        fp["frame"]: fp["prompt"] for fp in request.animation_prompts
                    },
                    max_frames=request.max_frames,
                    zoom=request.zoom or "0: (1.004)",
                    translation_x=request.translation_x or "0:(10*sin(2*3.14*t/10))",
                    translation_y=request.translation_y or "0:(0)",
                    rotation_3d_x=request.rotation_3d_x or "0:(0)",
                    rotation_3d_y=request.rotation_3d_y or "0:(0)",
                    rotation_3d_z=request.rotation_3d_z or "0:(0)",
                    translation_z="0:(0)",
                    fps=request.fps,
                ),
                content_type="video/mp4",
                filename=f"gooey.ai animation {request.animation_prompts}.mp4",
            )[0]
        except RuntimeError as e:
            msg = "\n\n".join(e.args).lower()
            if "key frame string not correctly formatted" in msg:
                raise UserError(str(e)) from e
