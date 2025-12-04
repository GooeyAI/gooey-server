from __future__ import annotations

import json
import os
import tempfile
import typing
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from textwrap import dedent

import gooey_gui as gui
import requests
from django.db.models import Q
from pydantic import BaseModel
from requests.utils import CaseInsensitiveDict

from ai_models.models import AIModelSpec
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import UserError, ffmpeg, ffprobe
from daras_ai_v2.fal_ai import generate_on_fal
from daras_ai_v2.functional import get_initializer
from daras_ai_v2.language_model_openai_realtime import yield_from
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.safety_checker import SAFETY_CHECKER_MSG, safety_checker
from daras_ai_v2.variables_widget import render_prompt_vars
from usage_costs.cost_utils import record_cost_auto
from usage_costs.models import ModelSku
from widgets.switch_with_section import switch_with_section


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
        audio_inputs: dict[str, typing.Any] | None = None

    class ResponseModel(BaseModel):
        output_videos: dict[str, HttpUrlStr]

    def run_v2(
        self, request: VideoGenPage.RequestModel, response: VideoGenPage.ResponseModel
    ) -> typing.Iterator[str | None]:
        if not request.selected_models:
            raise UserError("Please select at least one model")

        yield from self.run_safety_checker(request)

        q = Q()
        for model_name in request.selected_models:
            q |= Q(name__icontains=model_name)
        models = AIModelSpec.objects.filter(q)

        if request.selected_audio_model:
            audio_model = AIModelSpec.objects.get(name=request.selected_audio_model)
        else:
            audio_model = None

        progress_q = Queue()
        progress = {model.model_id: "" for model in models}
        response.output_videos = {model.name: None for model in models}
        with ThreadPoolExecutor(
            max_workers=len(models), initializer=get_initializer()
        ) as pool:
            fs = [
                pool.submit(
                    generate_video,
                    model=model,
                    inputs=request.inputs | dict(enable_safety_checker=False),
                    audio_model=audio_model,
                    audio_inputs=request.audio_inputs,
                    progress_q=progress_q,
                    output_videos=response.output_videos,
                )
                for model in models
            ]
            # print(f"{fs=}")
            yield f"Running {', '.join(model.label for model in models)}"

            while not all(fut.done() for fut in fs):
                model_id, msg = progress_q.get()
                if not msg:
                    continue
                progress[model_id] = msg
                yield "\n".join(progress.values())
            for fut in fs:
                fut.result()

    def run_safety_checker(
        self, request: VideoGenPage.RequestModel
    ) -> typing.Iterator[str | None]:
        if self.request.user.disable_safety_checker:
            return
        for inputs in [request.inputs, request.audio_inputs]:
            if not inputs:
                continue
            for key in ["prompt", "negative_prompt"]:
                text = inputs.get(key)
                if not text:
                    continue
                # Render any template variables in the prompt
                inputs[key] = render_prompt_vars(inputs[key], gui.session_state)
                yield "Running safety checker..."
                safety_checker(text=text)

    def render(self):
        self.available_models = CaseInsensitiveDict(
            {
                model.name: model
                for model in AIModelSpec.objects.filter(
                    category=AIModelSpec.Categories.video
                )
            }
        )
        self.available_audio_models = CaseInsensitiveDict(
            {
                model.name: model
                for model in AIModelSpec.objects.filter(
                    category=AIModelSpec.Categories.audio
                )
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
    model: AIModelSpec,
    inputs: dict,
    audio_model: AIModelSpec | None,
    audio_inputs: dict[str, typing.Any] | None,
    progress_q: Queue[tuple[str, str | None]],
    output_videos: dict[str, str],
):
    # print(f"{model=} {inputs=} {audio_model=} {audio_inputs=}")
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
        video_url = get_url_from_result(video_out)
        output_videos[model.name] = video_url
        # print(f"{video_url=}")
        if audio_model and audio_inputs:
            progress_q.put((model.model_id, f"Generating audio with {audio_model}..."))
            output_videos[model.name] = generate_audio(
                video_url, inputs, audio_model, audio_inputs
            )
    finally:
        progress_q.put((model.model_id, None))


def generate_audio(
    video_url: str,
    inputs: dict,
    audio_model: AIModelSpec,
    audio_inputs: dict[str, typing.Any],
) -> str:
    duration = float(ffprobe(video_url)["streams"][0]["duration"])
    duration_props = resolve_field_anyof(
        extract_openapi_schema(audio_model.schema, "request")
        .get("properties", {})
        .get("duration", {})
    )
    minimum = duration_props.get("minimum")
    maximum = duration_props.get("maximum")
    if minimum:
        duration = max(minimum, duration)
    if maximum:
        duration = min(maximum, duration)

    payload = {"video_url": video_url, "duration": duration} | audio_inputs
    if not payload.get("prompt"):
        payload["prompt"] = inputs.get("prompt")
    res = yield_from(generate_on_fal(audio_model.model_id, payload))
    record_cost_auto(audio_model.model_id, ModelSku.video_generation, 1)
    res_video = get_url_from_result(res.get("video"))
    res_audio = get_url_from_result(res.get("audio"))

    if res_video:
        return res_video
    elif res_audio:
        audio_url = get_url_from_result(res_audio)
        filename = f"{audio_model.label}_merged.mp4"
        return merge_audio_and_video(filename, audio_url, video_url)
    else:
        raise ValueError(f"No video/audio output from {audio_model.name}")


def render_video_gen_form(available_models: dict[str, AIModelSpec]):
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
    render_fields(
        key="inputs", available_models=available_models, selected_models=selected_models
    )


def render_audio_gen_form(available_audio_models: dict[str, AIModelSpec]):
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

        render_fields(
            key="audio_inputs",
            available_models=available_audio_models,
            selected_models=[selected_audio_model],
            skip_fields=["video_url", "duration"],
        )


def render_fields(
    key: str,
    available_models: dict[str, AIModelSpec],
    selected_models: list[str],
    skip_fields: typing.Iterable[str] = (),
):
    models = list(
        filter(None, (available_models.get(name) for name in selected_models))
    )
    if not models:
        return {}

    try:
        model_input_schemas = [
            schema
            for model in models
            if (schema := extract_openapi_schema(model.schema, "request"))
        ]
    except Exception as e:
        gui.error(f"Error getting input fields: {e}")
        return {}

    common_fields = set.intersection(
        *(set(schema.get("properties", {})) for schema in model_input_schemas)
    )

    schema = model_input_schemas[0]
    required_fields = set(schema.get("required", []))
    ordered_fields = schema.get("x-fal-order-properties") or list(common_fields)
    ordered_fields.sort(key=lambda x: x not in required_fields)
    old_inputs = gui.session_state.get(key) or {}
    new_inputs = {}

    for name in ordered_fields:
        if name not in common_fields or name in skip_fields:
            continue

        field = model_input_schemas[0]["properties"][name]
        label = field.get("title") or name.title()
        if name in required_fields:
            label = "##### " + label
        value = old_inputs.get(name) or field.get("default")

        new_inputs[name] = render_field(
            field=field, name=name, label=label, value=value
        )

    gui.session_state[key] = new_inputs


def render_field(*, field: dict, name: str, label: str, value: typing.Any):
    description = field.get("description")
    if description:
        help_text = dedent(description)
    else:
        help_text = None
    field = resolve_field_anyof(field)
    match field["type"]:
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
                label=label, value=value, help=help_text, options=field["enum"]
            )
            pytype = {"string": str, "integer": int, "number": float}[_type]
            return pytype(v)
        case "string":
            return gui.text_area(label=label, value=value, help=help_text)
        case "integer":
            minimum = field.get("minimum")
            maximum = field.get("maximum")
            if minimum and maximum:
                return gui.slider(
                    label=label,
                    min_value=minimum,
                    max_value=maximum,
                    value=value,
                    step=1,
                    help=help_text,
                )
            else:
                return gui.number_input(
                    label=label,
                    value=value,
                    help=help_text,
                    min_value=minimum,
                    max_value=maximum,
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
            return gui.checkbox(label=label, value=value, help=help_text)
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


def resolve_field_anyof(field: dict) -> dict:
    if field.get("type"):
        return field
    for props in field.get("anyOf", []):
        inner_type = props.get("type")
        if inner_type and inner_type != "null":
            return props
    return {"type": "object"}


def extract_openapi_schema(
    openapi_json: dict, schema_type: typing.Literal["request", "response"]
) -> dict | None:
    if openapi_json.get("properties"):
        return openapi_json

    endpoint_id = (
        openapi_json.get("info", {}).get("x-fal-metadata", {}).get("endpointId")
    )

    paths = openapi_json.get("paths", {})

    if schema_type == "request":
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
        return {}

    schema_name = schema_ref.split("/")[-1]
    return openapi_json.get("components", {}).get("schemas", {}).get(schema_name, {})


def get_url_from_result(result: dict | list | str | None) -> str | None:
    if not result:
        return None
    match result:
        case list():
            return result[0]
        case dict():
            return result.get("url")
        case _:
            return result


def merge_audio_and_video(filename: str, audio_url: str, video_url: str) -> str:
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
            "-i", video_path,
            "-stream_loop", "-1",
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path,
        )  # fmt:skip

        with open(output_path, "rb") as f:
            merged_video_bytes = f.read()

        return upload_file_from_bytes(filename, merged_video_bytes, "video/mp4")
