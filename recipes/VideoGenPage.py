from __future__ import annotations

import json
import typing
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from textwrap import dedent
import tempfile
import os
import requests
from furl import furl

import gooey_gui as gui
from django.db.models import Q
from pydantic import BaseModel

from ai_models.models import VideoModelSpec, Category
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import UserError, ffmpeg, ffprobe_metadata
from daras_ai_v2.fal_ai import generate_on_fal
from daras_ai_v2.functional import get_initializer
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.safety_checker import SAFETY_CHECKER_MSG, safety_checker
from daras_ai_v2.variables_widget import render_prompt_vars
from usage_costs.cost_utils import record_cost_auto
from usage_costs.models import ModelSku
from requests.utils import CaseInsensitiveDict
from widgets.switch_with_section import switch_with_section
from daras_ai.image_input import upload_file_from_bytes
from loguru import logger


class VideoGenPage(BasePage):
    title = Workflow.VIDEO_GEN.label
    workflow = Workflow.VIDEO_GEN
    slug_versions = ["video"]

    price_deferred = True

    class RequestModel(BasePage.RequestModel):
        selected_models: list[str]
        inputs: dict[str, typing.Any]

        # Audio generation settings
        selected_audio_model: str | None = None
        generate_audio: bool = False
        audio_inputs: dict[str, typing.Any] | None = None

    class ResponseModel(BaseModel):
        output_videos: dict[str, HttpUrlStr]

    def run_v2(
        self, request: VideoGenPage.RequestModel, response: VideoGenPage.ResponseModel
    ) -> typing.Iterator[str | None]:
        if not request.selected_models:
            raise UserError("Please select at least one model")

        for key in ["prompt", "negative_prompt"]:
            if not request.inputs.get(key):
                continue
            # Render any template variables in the prompt
            request.inputs[key] = render_prompt_vars(
                request.inputs[key], gui.session_state
            )
            # # Safety check if not disabled
            if self.request.user.disable_safety_checker:
                continue
            yield "Running safety checker..."
            safety_checker(text=request.inputs[key])

        q = Q()
        for model_name in request.selected_models:
            q |= Q(name__icontains=model_name)
        models = VideoModelSpec.objects.filter(q)

        progress_q = Queue()
        progress = {model.model_id: "" for model in models}
        response.output_videos = {model.name: None for model in models}
        with ThreadPoolExecutor(
            max_workers=len(models), initializer=get_initializer()
        ) as pool:
            fs = {
                model: pool.submit(
                    generate_video,
                    model,
                    request.inputs | dict(enable_safety_checker=False),
                    progress_q,
                )
                for model in models
            }
            # print(f"{fs=}")
            yield f"Running {', '.join(model.label for model in models)}"

            while not all(fut.done() for fut in fs.values()):
                model_id, msg = progress_q.get()
                if not msg:
                    continue
                progress[model_id] = msg
                yield "\n".join(progress.values())

            for model, fut in fs.items():
                response.output_videos[model.name] = fut.result()
            # print(f"{response.output_videos=}")

        yield from self.generate_sound_effects(request, response)

    def generate_sound_effects(
        self,
        request: "VideoGenPage.RequestModel",
        response: "VideoGenPage.ResponseModel",
    ) -> typing.Iterator[dict[str, str]]:
        merged_videos = {}

        if not request.generate_audio:
            return

        for video_model_name, video_url in response.output_videos.items():
            if not video_url:
                continue

            for key in ["prompt", "negative_prompt"]:
                if not request.audio_inputs.get(key):
                    continue

                # # Safety check if not disabled
                if self.request.user.disable_safety_checker:
                    continue
                yield "Running safety checker..."
                safety_checker(text=request.audio_inputs[key])

            yield f"Generating audio with {request.selected_audio_model}..."

            model = VideoModelSpec.objects.get(name=request.selected_audio_model)
            raw_dur = ffprobe_metadata(video_url)["format"]["duration"]
            payload = {"video_url": video_url, "duration": raw_dur}
            payload = payload | request.audio_inputs
            res = yield from generate_on_fal(model.model_id, payload)

            model_output_schemas = []
            try:
                model_output_schemas = get_output_fields([model])
            except Exception as e:
                logger.error(f"Error getting output fields: {e}")
                raise RuntimeError(f"Error getting output fields: {e}")

            if not model_output_schemas:
                raise RuntimeError(
                    f"No output fields returned from {request.selected_audio_model}"
                )

            fields = model_output_schemas[0].get("x-fal-order-properties")
            for field in fields:
                if "video" in field:
                    video_result = res.get("video")
                    video_url = self.get_url_from_result(video_result)
                    if video_url:
                        merged_videos[video_model_name] = video_url
                    break
                elif "audio" in field:
                    audio_result = res.get("audio")
                    audio_url = self.get_url_from_result(audio_result)
                    filename = (
                        furl(video_url.strip("/")).path.segments[-1].rsplit(".", 1)[0]
                        + "_gooey_ai_"
                        + request.selected_audio_model
                        + ".mp4"
                    )
                    if audio_url:
                        merged_videos[video_model_name] = self.merge_audio_and_video(
                            filename, audio_url, video_url
                        )
                    break
                else:
                    logger.warning(
                        f"Unknown field returned from {request.selected_audio_model}: {field.get('name')}"
                    )
                    raise RuntimeError(
                        f"Unknown field returned from {request.selected_audio_model}"
                    )

            response.output_videos.update(merged_videos)

    def get_url_from_result(self, result):
        if not result:
            return None

        if isinstance(result, list):
            if not result:
                return None
            result = result[0]

        if isinstance(result, dict):
            return result.get("url")

        if isinstance(result, str):
            return result

        return None

    def merge_audio_and_video(
        self, filename: str, audio_url: str, video_url: str
    ) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            audio_path = os.path.join(tmpdir, "audio.wav")
            output_path = os.path.join(tmpdir, "merged_video.mp4")

            video_response = requests.get(video_url)
            video_response.raise_for_status()
            with open(video_path, "wb") as f:
                f.write(video_response.content)

            audio_response = requests.get(audio_url)
            audio_response.raise_for_status()
            with open(audio_path, "wb") as f:
                f.write(audio_response.content)

            ffmpeg(
                "-i",
                video_path,
                "-i",
                audio_path,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-strict",
                "experimental",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                output_path,
            )

            with open(output_path, "rb") as f:
                merged_video_bytes = f.read()

            merged_url = upload_file_from_bytes(
                filename, merged_video_bytes, "video/mp4"
            )

            return merged_url

    def render(self):
        self.available_models = CaseInsensitiveDict(
            {
                model.name: model
                for model in VideoModelSpec.objects.filter(category=Category.Video)
            }
        )

        self.available_audio_models = CaseInsensitiveDict(
            {
                model.name: model
                for model in VideoModelSpec.objects.filter(category=Category.Audio)
            }
        )

        super().render()

    def get_raw_price(self, state: dict) -> float:
        return self.get_total_linked_usage_cost_in_credits(default=1000)

    def additional_notes(self) -> str | None:
        ret = ""
        selected_models = gui.session_state.get("selected_models", [])
        for name in selected_models:
            try:
                model = self.available_models[name]
            except KeyError:
                continue
            notes = model.pricing and model.pricing.notes
            if not notes:
                continue
            ret += "\n" + notes
        return ret

    def render_form_v2(self):
        render_video_gen_form(self.available_models)

        generate_audio = switch_with_section(
            label="##### Generate sound",
            key="generate_audio",
            control_keys=["selected_audio_model"],
            render_section=self.generate_audio_settings,
            disabled=not gui.session_state.get("selected_models"),
        )
        if not generate_audio:
            gui.session_state["selected_audio_model"] = None
            gui.session_state["audio_inputs"] = None

    def render_output(self):
        self.render_run_preview_output(gui.session_state, show_download_button=True)

    def render_run_preview_output(
        self, state: dict, show_download_button: bool = False
    ):
        output_videos = state.get("output_videos", {})
        if not output_videos:
            return

        for model_name, video_url in output_videos.items():
            try:
                model = self.available_models[model_name]
            except KeyError:
                continue
            if not video_url:
                continue
            gui.video(
                video_url,
                autoplay=True,
                show_download_button=show_download_button,
                caption=model.label,
            )

    def related_workflows(self) -> list:
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.DeforumSD import DeforumSDPage
        from recipes.Lipsync import LipsyncPage
        from recipes.DeforumSD import DeforumSDPage
        from recipes.Lipsync import LipsyncPage
        from recipes.VideoBots import VideoBotsPage

        return [
            LipsyncPage,
            DeforumSDPage,
            CompareText2ImgPage,
            VideoBotsPage,
        ]

    def render_description(self):
        gui.markdown(
            """
            Describe your scene and optional look-and-feel. Choose one or more video models to compare (Sora, Veo 3, Pika, Runway). Add an optional reference image for style or subject. Click Run to generate videos on the right. Adjust your prompt or settings and run again to iterate fast.
            """
        )

    def render_usage_guide(self):
        gui.markdown(
            """
            ### 🎬 How to Create Great AI Videos
            
            **✨ Prompt Tips:**
            - Describe subject, setting, and mood first
            - Add camera moves (e.g., dolly in, pan left)
            - Specify timing for beats: "end on a close-up"
            
            **📱 Best Practices:**
            - Use short sentences and clear directions
            - Try different models for varied styles
            - Iterate with negative prompts to refine results
            """
        )

    def generate_audio_settings(self):
        render_audio_gen_form(self.available_audio_models)


def generate_video(
    model: VideoModelSpec, inputs: dict, progress_q: Queue[tuple[str, str | None]]
) -> str:
    # print(f"{model=} {inputs=} {event=} {progress=} {output_videos=}")
    gen = generate_on_fal(model.model_id, inputs)
    try:
        while True:
            msg = next(gen)
            # print(f"{msg=}")
            progress_q.put((model.model_id, msg))
    except StopIteration as e:
        out = e.value
        # print(f"{out=}")
        video_out = out.get("video")
        if out.get("moderation_flagged"):
            raise UserError(SAFETY_CHECKER_MSG)
        elif not video_out:
            raise UserError(f"No video output: {out}")
        record_cost_auto(model.model_id, ModelSku.video_generation, 1)
        return video_out["url"]
        # print(f"{output_videos[model.name]=}")
    finally:
        progress_q.put((model.model_id, None))


def render_video_gen_form(available_models: dict[str, VideoModelSpec]):
    # normalize the selected model names
    gui.session_state["selected_models"] = [
        model.name
        for name in gui.session_state.get("selected_models", [])
        if (model := available_models.get(name))
    ]
    selected_models = gui.multiselect(
        label="###### Video Models",
        options=list(available_models.keys()),
        format_func=lambda x: available_models[x].label,
        key="selected_models",
        allow_none=True,
    )
    models = list(
        filter(None, (available_models.get(name) for name in selected_models))
    )
    if not models:
        return

    model_input_schemas = []
    try:
        model_input_schemas = get_input_fields(models)
    except Exception as e:
        logger.error(f"Error getting input fields: {e}")
        gui.error(f"Error getting input fields: {e}")
        return

    common_fields = set.intersection(
        *(set(schema.get("properties", {})) for schema in model_input_schemas)
    )
    schema = model_input_schemas[0]
    required_fields = set(schema.get("required", []))
    ordered_fields = schema.get("x-fal-order-properties") or list(common_fields)
    ordered_fields.sort(key=lambda x: x not in required_fields)
    old_inputs = gui.session_state.get("inputs") or {}
    new_inputs = {}

    for name in ordered_fields:
        if name not in common_fields:
            continue

        field = model_input_schemas[0]["properties"][name]
        label = field.get("title") or name.title()
        if name in required_fields:
            label = "##### " + label
        value = old_inputs.get(name) or field.get("default")

        new_inputs[name] = render_field(
            field=field, name=name, label=label, value=value
        )

    gui.session_state["inputs"] = new_inputs


def render_audio_gen_form(available_audio_models: dict[str, VideoModelSpec]):
    with gui.div(className="pt-1 pb-1"):
        gui.caption(
            "Automatically add sound effects. Note: Overwrites audio if present in video. "
        )

        current_audio_model = gui.session_state.get("selected_audio_model")
        if current_audio_model and current_audio_model not in available_audio_models:
            gui.session_state["selected_audio_model"] = None

        if not available_audio_models:
            return

        selected_audio_model = gui.selectbox(
            label="###### Sound generation model",
            options=list(available_audio_models.keys()),
            format_func=lambda x: available_audio_models[x].label,
            key="selected_audio_model",
            allow_none=False,
            disabled=not available_audio_models
            or not gui.session_state.get("selected_models"),
        )

        models = list(
            filter(
                None,
                (available_audio_models.get(name) for name in [selected_audio_model]),
            )
        )

        model_input_schemas = []
        try:
            model_input_schemas = get_input_fields(models)
        except Exception as e:
            logger.error(f"Error getting input fields: {e}")
            gui.error(f"Error getting input fields: {e}")
            return

        schema = model_input_schemas[0]
        required_fields = set(schema.get("required", []))
        ordered_fields = schema.get("x-fal-order-properties")
        ordered_fields.sort(key=lambda x: x not in required_fields)
        old_inputs = gui.session_state.get("audio_inputs") or {}
        new_inputs = {}

        skip_fields = ["video_url", "duration"]

        for name in ordered_fields:
            if name in skip_fields:
                continue
            field = model_input_schemas[0]["properties"][name]
            label = field.get("title") or name.title()
            value = old_inputs.get(name) or field.get("default")
            new_inputs[name] = render_field(
                field=field, name=name, label=label, value=value
            )
        gui.session_state["audio_inputs"] = new_inputs


def render_field(
    *,
    field: dict,
    name: str,
    label: str,
    value: typing.Any,
):
    description = field.get("description")
    if description:
        help_text = dedent(description)
    else:
        help_text = None

    match get_field_type(field):
        case "array" if "lora" in name or "url" in name:
            return gui.file_uploader(
                label=label,
                value=value,
                help=help_text,
                accept_multiple_files=True,
            )
        case "string" if "lora" in name or "url" in name:
            return gui.file_uploader(
                label=label,
                value=value,
                help=help_text,
            )
        case ("string" | "integer" | "number") as _type if field.get("enum"):
            v = gui.selectbox(
                label=label,
                value=value,
                help=help_text,
                options=field["enum"],
            )
            pytype = {"string": str, "integer": int, "number": float}[_type]
            return pytype(v)
        case "string":
            return gui.text_area(
                label=label,
                value=value,
                help=help_text,
            )
        case "integer":
            return gui.number_input(
                label=label,
                value=value,
                help=help_text,
                min_value=field.get("minimum"),
                max_value=field.get("maximum"),
                step=1,
            )
        case "number":
            return gui.number_input(
                label=label,
                value=value,
                help=help_text,
                min_value=field.get("minimum"),
                max_value=field.get("maximum"),
                step=0.1,
            )
        case "boolean":
            return gui.checkbox(
                label=label,
                value=value,
                help=help_text,
            )
        case "object":
            try:
                json_str = json.dumps(value, indent=2)
            except TypeError:
                json_str = str(value)
            json_str = gui.code_editor(
                label="",
                language="json",
                value=json_str,
                style=dict(maxHeight="300px"),
            )
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                gui.error("Invalid JSON")
            if not isinstance(value, dict):
                gui.error("Value must be a JSON object")


def get_field_type(field: dict) -> str:
    try:
        return field["type"]
    except KeyError:
        for props in field.get("anyOf", []):
            inner_type = props.get("type")
            if inner_type and inner_type != "null":
                return inner_type
        return "object"


def get_input_fields(models: list[VideoModelSpec]):
    return [
        schema
        for model in models
        if (schema := extract_schema_from_openapi(model.schema, "input"))
    ]


def get_output_fields(models: list[VideoModelSpec]):
    return [
        schema
        for model in models
        if (schema := extract_schema_from_openapi(model.schema, "output"))
    ]


def extract_schema_from_openapi(openapi_json: dict, schema_type: str) -> dict | None:
    endpoint_id = (
        openapi_json.get("info", {}).get("x-fal-metadata", {}).get("endpointId")
    )

    paths = openapi_json.get("paths", {})

    if schema_type == "input":
        path_key = f"/{endpoint_id}"
        method_data = paths.get(path_key, {}).get("post", {})
        schema_ref = (
            method_data.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
    else:  # output
        path_key = f"/{endpoint_id}/requests/{{request_id}}"
        method_data = paths.get(path_key, {}).get("get", {})
        schema_ref = (
            method_data.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )

    if not schema_ref:
        return None

    schema_name = schema_ref.split("/")[-1]
    return openapi_json.get("components", {}).get("schemas", {}).get(schema_name, {})
