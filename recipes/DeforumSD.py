import re
import typing
from functools import partial

import gooey_gui as gui
from django.db.models import TextChoices
from pydantic import BaseModel
from typing_extensions import TypedDict

from bots.models import Workflow
from daras_ai_v2 import icons
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.gpu_server import call_celery_task_outfile
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.pydantic_validation import FieldHttpUrl
from daras_ai_v2.safety_checker import safety_checker
from recipes.BulkRunner import list_view_editor


CREDITS_PER_FRAME = 1.5
MODEL_ESTIMATED_TIME_PER_FRAME = 2.4  # seconds


class AnimationModels(TextChoices):
    protogen_2_2 = ("Protogen_V2.2.ckpt", "Protogen V2.2 (darkstorm2150)")
    epicdream = ("epicdream.safetensors", "epiCDream [Deprecated] (epinikion)")

    @classmethod
    def _deprecated(cls):
        return {cls.epicdream}


class _AnimationPrompt(TypedDict):
    frame: str
    prompt: str


AnimationPrompts = list[_AnimationPrompt]


class DeforumSDPage(BasePage):
    title = "AI Animation Generator"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/media/users/kxmNIYAOJbfOURxHBKNCWeUSKiP2/dd88c110-88d6-11ee-9b4f-2b58bd50e819/animation.gif"
    workflow = Workflow.DEFORUM_SD
    slug_versions = ["DeforumSD", "animation-generator"]

    sane_defaults = dict(
        fps=12,
        seed=42,
        selected_model=AnimationModels.protogen_2_2.name,
    )

    class RequestModel(BasePage.RequestModel):
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
        fps_slider = gui.session_state["fps"]

        # keep track of the prev value of fps slider to keep slider and preset in sync
        prev_fps_slider = gui.session_state.setdefault("-prev-fps", fps_slider)
        gui.session_state["-prev-fps"] = fps_slider
        fps_preset = gui.session_state.setdefault("-fps-preset", str(fps_slider))
        if prev_fps_slider != fps_slider:
            # fps slider changed, update the fps_preset
            gui.session_state["-fps-preset"] = str(fps_slider)
        elif fps_preset != str(fps_slider):
            # fps preset changed, update the fps slider
            gui.session_state["fps"] = int(fps_preset)

        gui.write("#### 👩‍💻 Animation Prompts")
        gui.caption(
            """
            Describe the scenes or series of images that you want to generate into an animation. 
            You can add as many prompts as you like. Mention the keyframe seconds for each prompt i.e. the transition point from the first prompt to the next.
            """
        )
        gui.write("#### Step 1: Draft & Refine Keyframes")

        animation_prompts_editor(prev_fps_slider, fps_slider)

        gui.write("#### Step 2: Increase Animation Quality")
        gui.caption(
            """
            Once you like your keyframes, increase your frames per second for high quality.
            """
        )

        options = {
            "2": "Draft: 2 FPS",
            "10": "Stop-motion: 10 FPS",
            "24": "Film: 24 FPS",
        }
        gui.horizontal_radio(
            label="",
            options=options,
            format_func=options.__getitem__,
            key="-fps-preset",
            checked_by_default=False,
        )

        gui.slider(label="", min_value=2, max_value=30, key="fps")

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
        assert get_last_frame(prompt_list) <= max_frames, (
            "Please make sure that Frame Count matches the Animation Prompts"
        )

    def render_usage_guide(self):
        youtube_video("sUvica6UuQU")

    def render_settings(self):
        col1, col2 = gui.columns(2)
        with col1:
            enum_selector(
                AnimationModels,
                label="Choose your preferred AI Animation Model",
                key="selected_model",
                use_selectbox=True,
            )

            gui.selectbox("Animation Mode", key="animation_mode", options=["2D", "3D"])

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

    def render_description(self):
        gui.markdown(
            """
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

    def render_run_preview_output(self, state: dict):
        display = self.preview_input(state)
        gui.markdown("```lua\n" + display + "\n```")

        gui.video(state.get("output_video"), autoplay=True)

    @classmethod
    def preview_input(cls, state: dict) -> str:
        animation_prompts = state.get("animation_prompts", [])
        display = "\n\n".join(
            [f"{fp['prompt']} [{fp['frame']}]" for fp in animation_prompts]
        )
        return display

    def run(self, state: dict):
        request: DeforumSDPage.RequestModel = self.RequestModel.parse_obj(state)
        model = AnimationModels[request.selected_model]

        if model in AnimationModels._deprecated():
            raise UserError(
                f"The selected model `{model}` is deprecated. Please select a different model."
            )

        yield f"Running {model.label}..."

        if not self.request.user.disable_safety_checker:
            safety_checker(text=self.preview_input(state))

        try:
            state["output_video"] = call_celery_task_outfile(
                "deforum",
                pipeline=dict(
                    model_id=model.value,
                    seed=request.seed,
                ),
                inputs=dict(
                    animation_mode=request.animation_mode,
                    animation_prompts={
                        fp["frame"]: fp["prompt"] for fp in request.animation_prompts
                    },
                    max_frames=request.max_frames,
                    zoom=request.zoom or "0:(1)",
                    translation_x=request.translation_x or "0:(0)",
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


_icon_width = "1.2rem"


class ZoomPanSettings(BaseModel):
    zoom: float
    translation_x: float
    translation_y: float
    rotation_3d_x: float
    rotation_3d_y: float
    rotation_3d_z: float


def animation_prompts_editor(
    prev_fps: int,
    fps: int,
    key: str = "animation_prompts",
):
    use_3d = gui.session_state.get("animation_mode") == "3D"

    zoom_kf = parse_key_frames(gui.session_state.get("zoom") or "")
    translation_x_kf = parse_key_frames(gui.session_state.get("translation_x") or "")
    translation_y_kf = parse_key_frames(gui.session_state.get("translation_y") or "")
    rotation_3d_x_kf = parse_key_frames(gui.session_state.get("rotation_3d_x") or "")
    rotation_3d_y_kf = parse_key_frames(gui.session_state.get("rotation_3d_y") or "")
    rotation_3d_z_kf = parse_key_frames(gui.session_state.get("rotation_3d_z") or "")

    list_view_editor(
        key=key,
        render_inputs=partial(
            animation_prompts_list_item,
            key=key,
            prev_fps=prev_fps,
            fps=fps,
            use_3d=use_3d,
            zoom_kf=zoom_kf,
            translation_x_kf=translation_x_kf,
            translation_y_kf=translation_y_kf,
            rotation_3d_x_kf=rotation_3d_x_kf,
            rotation_3d_y_kf=rotation_3d_y_kf,
            rotation_3d_z_kf=rotation_3d_z_kf,
        ),
    )

    gui.session_state["zoom"] = key_frames_to_str(zoom_kf, default_val=1)
    gui.session_state["translation_x"] = key_frames_to_str(translation_x_kf)
    gui.session_state["translation_y"] = key_frames_to_str(translation_y_kf)
    if use_3d:
        gui.session_state["rotation_3d_x"] = key_frames_to_str(rotation_3d_x_kf)
        gui.session_state["rotation_3d_y"] = key_frames_to_str(rotation_3d_y_kf)
        gui.session_state["rotation_3d_z"] = key_frames_to_str(rotation_3d_z_kf)
    else:
        gui.session_state.pop("rotation_3d_x", None)
        gui.session_state.pop("rotation_3d_y", None)
        gui.session_state.pop("rotation_3d_z", None)

    with gui.div(
        className="border rounded mb-3 pb-0 p-3 d-flex gap-2",
        style=dict(backgroundColor="rgb(var(--bs-light-rgb))"),
    ):
        gui.html(
            f'<i class="mt-3 pt-1 fa-duotone fa-solid fa-timer fa-lg" style="width: {_icon_width}"></i>'
        )
        with gui.div(className="mt-2 ms-1"):
            gui.write("Total Duration")
        max_seconds = gui.number_input(
            label="",
            key="max_seconds",
            min_value=0,
            step=1,
            value=frames_to_seconds(gui.session_state.get("max_frames") or 100, fps),
        )
        gui.session_state["max_frames"] = seconds_to_frames(max_seconds, fps)
        with gui.div(className="mt-2"):
            gui.write("seconds")


def animation_prompts_list_item(
    item_key: str,
    del_key: str,
    item_dict: dict,
    *,
    key: str,
    prev_fps: int,
    fps: int,
    use_3d: bool = False,
    zoom_kf: dict,
    translation_x_kf: dict,
    translation_y_kf: dict,
    rotation_3d_x_kf: dict,
    rotation_3d_y_kf: dict,
    rotation_3d_z_kf: dict,
):
    prev_d = None
    next_d = None
    animation_prompts = gui.session_state.get(key, [])
    try:
        idx = animation_prompts.index(item_dict)
        if idx > 0:
            prev_d = animation_prompts[idx - 1]
        if idx < len(animation_prompts) - 1:
            next_d = animation_prompts[idx + 1]
    except (ValueError, IndexError):
        idx = len(animation_prompts) - 1

    frame = int(item_dict["frame"])

    min_seconds = prev_d and prev_d.get("_seconds") or 0
    max_seconds = (
        next_d and next_d.get("_seconds") or gui.session_state.get("max_seconds", 100)
    )

    with gui.div(
        className="border rounded mb-3 pb-0 p-3",
        style=dict(backgroundColor="rgb(var(--bs-light-rgb))"),
    ):
        with gui.div(className="d-flex justify-content-between"):
            with gui.div(className="d-flex gap-3 align-items-start"):
                gui.html(
                    f'<i class="mt-3 pt-1 fa-duotone fa-solid fa-timer fa-lg" style="width: {_icon_width}"></i>',
                )

                # an arbitrary scaling factor to make the movement consistent across different fps
                fps_scaling = 1.2

                fps1 = (prev_fps + fps_scaling) ** fps_scaling
                zp_settings = ZoomPanSettings(
                    zoom=zoom_kf.pop(frame, 1.0) ** prev_fps,
                    translation_x=translation_x_kf.pop(frame, 0.0) * fps1,
                    translation_y=translation_y_kf.pop(frame, 0.0) * fps1,
                    rotation_3d_x=rotation_3d_x_kf.pop(frame, 0.0) * fps1,
                    rotation_3d_y=rotation_3d_y_kf.pop(frame, 0.0) * fps1,
                    rotation_3d_z=rotation_3d_z_kf.pop(frame, 0.0) * fps1,
                )

                item_dict["_seconds"] = seconds = gui.number_input(
                    label="",
                    key=item_key + ":seconds",
                    value=frames_to_seconds(frame, fps),
                    min_value=min_seconds,
                    max_value=max_seconds,
                    step=round(1 / fps, 2),
                )
                item_dict["frame"] = frame = seconds_to_frames(seconds, fps)
                if not min_seconds <= seconds <= max_seconds:
                    gui.error("Seconds must be between the previous and next frame")

                zp_settings = zoom_pan_button_with_dialog(
                    item_key=item_key,
                    seconds=seconds,
                    max_seconds=max_seconds,
                    use_3d=use_3d,
                    settings=zp_settings,
                )

                fps2 = (fps + fps_scaling) ** fps_scaling
                zoom_kf[frame] = zp_settings.zoom ** (1 / fps)
                translation_x_kf[frame] = zp_settings.translation_x / fps2
                translation_y_kf[frame] = zp_settings.translation_y / fps2
                if use_3d:
                    rotation_3d_x_kf[frame] = zp_settings.rotation_3d_x / fps2
                    rotation_3d_y_kf[frame] = zp_settings.rotation_3d_y / fps2
                    rotation_3d_z_kf[frame] = zp_settings.rotation_3d_z / fps2

            with gui.div(className="d-flex gap-4 align-items-start mt-2 me-1"):
                if gui.button(
                    icons.add,
                    key=item_key + ":add",
                    type="link",
                ):
                    next_second = round((float(seconds) + float(max_seconds)) / 2, 2)
                    next_frame = seconds_to_frames(next_second, fps)
                    animation_prompts.insert(idx + 1, dict(frame=next_frame, prompt=""))

                gui.button(
                    icons.delete,
                    key=del_key,
                    type="link",
                    className="text-danger",
                )

        with gui.div(className="d-flex gap-3"):
            gui.html(
                f'<i class="mt-3 fa-duotone fa-solid fa-scroll fa-lg" style="width: {_icon_width}"></i>'
            )
            with gui.div(className="w-100"):
                item_dict["prompt"] = gui.text_area(
                    label="",
                    key=item_key + ":prompt",
                    value=item_dict["prompt"],
                    height=100,
                    className="w-100",
                )


def zoom_pan_button_with_dialog(
    *,
    item_key: str,
    seconds: float,
    max_seconds: float,
    use_3d: bool,
    settings: ZoomPanSettings,
) -> ZoomPanSettings:
    zoom_pan_modal = gui.use_alert_dialog(key=item_key + ":zoom-pan-modal")
    if gui.button(
        '<i class="fa-solid fa-camera-movie"></i>',
        key=zoom_pan_modal.open_btn_key,
        type="link",
        className="mt-2",
    ):
        zoom_pan_modal.set_open(True)

    if zoom_pan_modal.is_open:
        zoom_pan_dialog(
            zoom_pan_modal, item_key, seconds, max_seconds, use_3d, settings
        )

    with gui.div(className="mt-2 d-none d-lg-block me-2"):
        gui.caption(
            get_zoom_pan_summary(
                zoom=settings.zoom,
                translation_x=settings.translation_x,
                translation_y=settings.translation_y,
                rotation_3d_x=settings.rotation_3d_x,
                rotation_3d_y=settings.rotation_3d_y,
                rotation_3d_z=settings.rotation_3d_z,
            ),
        )

    return settings


def zoom_pan_dialog(
    ref: gui.AlertDialogRef,
    item_key: str,
    seconds: float,
    max_seconds: float,
    use_3d: bool,
    settings: ZoomPanSettings,
):
    with gui.alert_dialog(ref=ref, modal_title="### Zoom/Pan", large=True):
        gui.write(
            f"#### Keyframe second {seconds} until {max_seconds}",
        )
        gui.caption(
            f"Starting at second {seconds} and until second {max_seconds}, how do you want the camera to move?"
        )
        settings.zoom = key_frame_slider(
            label="###### Zoom",
            caption="How should the camera zoom in or out? This setting scales the canvas size, multiplicatively. 1 is static, with numbers greater than 1 moving forward (or zooming in) and numbers less than 1 moving backwards (or zooming out).",
            min_value=0.1,
            max_value=2,
            key=item_key + ":zoom",
            value=settings.zoom,
        )
        settings.translation_x = key_frame_slider(
            label="""###### Horizontal Pan""",
            caption="How should the camera pan horizontally? This parameter uses positive values to move right and negative values to move left.",
            min_value=-10,
            max_value=10,
            key=item_key + ":translation_x",
            value=settings.translation_x,
        )
        settings.translation_y = key_frame_slider(
            label="""###### Vertical Pan""",
            caption="How should the camera pan vertically? This parameter uses positive values to move up and negative values to move down.",
            min_value=-10,
            max_value=10,
            key=item_key + ":translation_y",
            value=settings.translation_y,
        )
        if not use_3d:
            return
        settings.rotation_3d_x = key_frame_slider(
            label="""###### Tilt Up/Down""",
            caption="Tilts the camera up or down in degrees per second. This parameter uses positive values to tilt up and negative values to tilt down.",
            min_value=-10,
            max_value=10,
            key=item_key + ":rotation_3d_x",
            value=settings.rotation_3d_x,
        )
        settings.rotation_3d_y = key_frame_slider(
            label="###### Pan Left/Right",
            caption="Pans the canvas left or right in degrees per second. This parameter uses positive values to pan right and negative values to pan left.",
            min_value=-10,
            max_value=10,
            key=item_key + ":rotation_3d_y",
            value=settings.rotation_3d_y,
        )
        settings.rotation_3d_z = key_frame_slider(
            label="###### Roll Clockwise/Counterclockwise",
            caption="Gradually moves the camera on a focal axis. Roll the camera clockwise or counterclockwise in a specific degree per second. This parameter uses positive values to roll counterclockwise and negative values to roll clockwise.",
            min_value=-10,
            max_value=10,
            key=item_key + ":rotation_3d_z",
            value=settings.rotation_3d_z,
        )


def get_zoom_pan_summary(
    *,
    zoom: float,
    translation_x: float,
    translation_y: float,
    rotation_3d_x: float,
    rotation_3d_y: float,
    rotation_3d_z: float,
) -> str:
    parts = []
    if 0.999 < zoom < 1.001:
        pass
    elif zoom < 1:
        parts.append(f"Out: {zoom:.3f}×")
    else:
        parts.append(f"In: {zoom:.3f}×")
    if -0.001 < translation_x < 0.001:
        pass
    elif translation_x > 0:
        parts.append(f"Right: {translation_x:.3f} ➡️")
    else:
        parts.append(f"Left: {translation_x:.3f} ⬅️")
    if -0.001 < translation_y < 0.001:
        pass
    elif translation_y > 0:
        parts.append(f"Up: {translation_y:.3f} ⬆️")
    else:
        parts.append(f"Down: {-translation_y:.3f} ⬇️")
    if -0.001 < rotation_3d_x < 0.001:
        pass
    elif rotation_3d_x > 0:
        parts.append(f"Tilt ⤴: {rotation_3d_x:.3f}°")
    else:
        parts.append(f"Tilt ⤵: {-rotation_3d_x:.3f}°")
    if -0.001 < rotation_3d_y < 0.001:
        pass
    elif rotation_3d_y > 0:
        parts.append(f"Pan ↪: {rotation_3d_y:.3f}°")
    else:
        parts.append(f"Pan ↩: {-rotation_3d_y:.3f}°")
    if -0.001 < rotation_3d_z < 0.001:
        pass
    elif rotation_3d_z > 0:
        parts.append(f"Roll ↺: {rotation_3d_z:.3f}°")
    else:
        parts.append(f"Roll ↻: {-rotation_3d_z:.3f}°")
    return " • ".join(parts)


def key_frame_slider(
    label: str,
    caption: str,
    key: str,
    min_value: float,
    max_value: float,
    value: float,
):
    col1, col2 = gui.columns([1, 1])
    with col1:
        slider_value = gui.slider(
            label=label,
            key=key,
            min_value=min_value,
            max_value=max_value,
            step=0.001,
            value=value,
        )
    with col2:
        gui.caption(caption)
    return slider_value


def get_last_frame(prompt_list: list) -> int:
    return max(fp["frame"] for fp in prompt_list)


def frames_to_seconds(frames: int, fps: int) -> float:
    return round(frames / int(fps), 2)


def seconds_to_frames(seconds: float, fps: int) -> int:
    return int(float(seconds) * int(fps))


def key_frames_to_str(key_frames: dict[int, float], default_val: float = 0.0) -> str:
    key_frames.setdefault(0, default_val)
    return ", ".join(
        f"{key}:({frame})"
        for key, frame in key_frames.items()
        if key == 0 or not default_val - 0.001 < frame < default_val + 0.001
    )


# from https://github.com/deforum-art/deforum-stable-diffusion/blob/03be26aebc4aec6e3a0298c8d3e271c672034f59/helpers/animation.py#L337
def parse_key_frames(string, prompt_parser=None):
    # because math functions (i.e. sin(t)) can utilize brackets
    # it extracts the value in form of some stuff
    # which has previously been enclosed with brackets and
    # with a comma or end of line existing after the closing one
    pattern = r"((?P<frame>[0-9]+):[\s]*\((?P<param>[\S\s]*?)\)([,][\s]?|[\s]?$))"
    frames = dict()
    for match_object in re.finditer(pattern, string):
        frame = int(match_object.groupdict()["frame"])
        param = match_object.groupdict()["param"]
        if prompt_parser:
            frames[frame] = prompt_parser(param)
        else:
            try:
                frames[frame] = float(param)
            except (ValueError, TypeError):
                pass
    # if frames == {} and len(string) != 0:
    #     raise RuntimeError("Key Frame string not correctly formatted")
    return frames
