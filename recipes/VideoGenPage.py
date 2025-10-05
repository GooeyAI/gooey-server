from __future__ import annotations

import json
import typing
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from textwrap import dedent

import gooey_gui as gui
from django.db.models import Q
from pydantic import BaseModel
from requests.utils import CaseInsensitiveDict

from ai_models.models import VideoModelSpec
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.fal_ai import generate_on_fal
from daras_ai_v2.functional import get_initializer
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.safety_checker import SAFETY_CHECKER_MSG, safety_checker
from daras_ai_v2.variables_widget import render_prompt_vars
from usage_costs.cost_utils import record_cost_auto
from usage_costs.models import ModelSku


class VideoGenPage(BasePage):
    title = Workflow.VIDEO_GEN.label
    workflow = Workflow.VIDEO_GEN
    slug_versions = ["video"]

    price_deferred = True

    class RequestModel(BasePage.RequestModel):
        selected_models: list[str]
        inputs: dict[str, typing.Any]

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
            # Safety check if not disabled
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

    def render(self):
        self.available_models = CaseInsensitiveDict(
            {model.name: model for model in VideoModelSpec.objects.all()}
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

    common_fields = set.intersection(
        *(set(model.schema["properties"]) for model in models)
    )
    schema = models[0].schema
    required_fields = set(schema.get("required", []))
    ordered_fields = schema.get("x-fal-order-properties") or list(common_fields)
    ordered_fields.sort(key=lambda x: x not in required_fields)
    old_inputs = gui.session_state.get("inputs", {})
    new_inputs = {}

    for name in ordered_fields:
        if name not in common_fields:
            continue

        field = models[0].schema["properties"][name]
        label = field.get("title") or name.title()
        if name in required_fields:
            label = "##### " + label
        value = old_inputs.get(name) or field.get("default")

        new_inputs[name] = render_field(
            field=field, name=name, label=label, value=value
        )

    gui.session_state["inputs"] = new_inputs


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
        case "string" if field.get("enum"):
            return gui.selectbox(
                label=label,
                value=value,
                help=help_text,
                options=field["enum"],
            )
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
