from __future__ import annotations

import html
import os
import tempfile
import typing
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

import gooey_gui as gui
import requests
from django.db.models import Q
from pydantic import BaseModel
from requests.utils import CaseInsensitiveDict

from ai_models.llm_openapi import AudioModelMarker, VideoModelMarker
from ai_models.models import AIModelSpec
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes, truncate_text_words
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import PaymentRequired, UserError, ffmpeg, ffprobe
from daras_ai_v2.fal_ai import generate_on_fal, format_pricing_notes
from daras_ai_v2.functional import get_initializer
from daras_ai_v2.language_model_openai_realtime import yield_from
from daras_ai_v2.preview_img import media_preview_img
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.safety_checker import SAFETY_CHECKER_MSG, safety_checker
from daras_ai_v2.schema_model_form import (
    build_combined_input_schema,
    extract_openapi_schema,
    get_url_from_result,
    render_fields,
    resolve_field_anyof,
)
from daras_ai_v2.variables_widget import render_prompt_vars
from usage_costs.models import ModelSku
from widgets.switch_with_section import switch_with_section


SKIP_AUDIO_INPUT_FIELDS = ["video_url", "duration"]


class VideoGenPage(BasePage):
    title = Workflow.VIDEO_GEN.label
    workflow = Workflow.VIDEO_GEN
    slug_versions = ["video"]

    price_deferred = True

    class RequestModel(BasePage.RequestModel):
        selected_models: list[VideoModelMarker]
        inputs: dict[str, typing.Any]

        # Audio generation settings
        selected_audio_model: AudioModelMarker | None = None
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
            q |= Q(name__iexact=model_name)
        models = AIModelSpec.objects.filter(q)

        if not models.exists():
            raise UserError(
                f"Model {request.selected_models} not found. Should be one of: "
                + ", ".join(
                    AIModelSpec.objects.filter(category=AIModelSpec.Categories.video)
                    .order_for_frontend()
                    .values_list("name", flat=True)
                )
            )

        paid_only_models = models.filter(paid_only=True)
        if not self.current_workspace.is_paying and paid_only_models.exists():
            raise PaymentRequired(
                list(paid_only_models.values_list("label", flat=True))
            )

        if request.selected_audio_model:
            audio_model = AIModelSpec.objects.get(name=request.selected_audio_model)
            if not self.current_workspace.is_paying and audio_model.paid_only:
                raise PaymentRequired([audio_model.label])
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
        video_models = list(
            AIModelSpec.objects.filter(
                category=AIModelSpec.Categories.video
            ).order_for_frontend(
                selected_models=gui.session_state.get("selected_models")
            )
        )

        self.available_models = CaseInsensitiveDict(
            {model.name: model for model in video_models}
        )
        self.available_audio_models = CaseInsensitiveDict(
            {
                model.name: model
                for model in AIModelSpec.objects.filter(
                    category=AIModelSpec.Categories.audio
                ).order_for_frontend(
                    selected_models=gui.session_state.get("selected_audio_model")
                )
            }
        )
        super().render()

    def get_raw_price(self, state: dict) -> float:
        return self.get_total_linked_usage_cost_in_credits(default=1000)

    def additional_notes(self) -> str | None:
        selected_names = gui.session_state.get("selected_models") or []
        models = [self.available_models.get(name) for name in selected_names]

        audio_model_name = gui.session_state.get("selected_audio_model")
        if audio_model_name:
            models.append(self.available_audio_models.get(audio_model_name))

        return format_pricing_notes(
            {model.model_id: model.label for model in models if model},
            sku=ModelSku.fal_billable_units,
        )

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
        self.render_run_preview_output(gui.session_state, preview=False)

    def render_run_preview_output(self, state: dict, preview=True):
        output_videos = state.get("output_videos", {})
        if not output_videos:
            return

        # Get the prompt from the inputs
        prompt = state.get("inputs", {}).get("prompt", "")

        for model_name, video_url in output_videos.items():
            if not video_url:
                continue
            try:
                label = self.available_models[model_name].label
            except KeyError:
                label = model_name
            # Render video first
            gui.video(
                video_url,
                autoplay=True,
                show_download_button=not preview,
                previewImg=media_preview_img(video_url) if preview else None,
            )
            gui.caption(label)

        if preview and prompt:
            prompt_preview = truncate_text_words(html.escape(prompt), 200)
            gui.write(
                f'<i class="fa-regular fa-lightbulb-on" style="fontSize: 0.8rem; vertical-align: 0.05rem"></i>&nbsp;{prompt_preview}',
                unsafe_allow_html=True,
            )

    def related_workflows(self) -> list:
        from recipes.DeforumSD import DeforumSDPage
        from recipes.ImageGenPage import ImageGenPage
        from recipes.Lipsync import LipsyncPage
        from recipes.VideoBots import VideoBotsPage

        return [
            LipsyncPage,
            DeforumSDPage,
            ImageGenPage,
            VideoBotsPage,
        ]

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

    @classmethod
    def preview_output(cls, state: dict) -> str | None:
        ret = super().preview_output(state)
        if ret and "fal.media" in ret:
            # fal.media urls dont have thumbnails, don't render in previews
            return None
        else:
            return ret

    @classmethod
    def get_tool_call_schema(cls, state: dict) -> dict[str, typing.Any]:
        properties = super().get_tool_call_schema(state)

        selected_models = state.get("selected_models") or []
        video_models = AIModelSpec.objects.filter(name__in=selected_models)
        if inputs_schema := build_combined_input_schema(video_models):
            properties["inputs"] = inputs_schema
            # since inputs depends on selected_models, we currently cannot allow the model to change it
            properties.pop("selected_models", None)
        else:
            properties.pop("inputs", None)

        selected_audio_model = state.get("selected_audio_model")
        if selected_audio_model:
            audio_models = AIModelSpec.objects.filter(name=selected_audio_model)
            if audio_inputs_schema := build_combined_input_schema(
                audio_models,
                skip_fields=SKIP_AUDIO_INPUT_FIELDS,
            ):
                properties["audio_inputs"] = audio_inputs_schema
            # since audio_inputs depends on selected_audio_model, we currently cannot allow the model to change it
            properties.pop("selected_audio_model", None)
        else:
            properties.pop("audio_inputs", None)

        return properties


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
        video_url = get_url_from_result(video_out)
        output_videos[model.name] = video_url
        # print(f"{video_url=}")
        if audio_model and audio_inputs:
            progress_q.put((model.model_id, f"Generating audio with {audio_model}..."))
            output_videos[model.name] = generate_audio(
                video_url,
                inputs,
                audio_model,
                audio_inputs,
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
        format_func=lambda x: available_models[x].display_html(),
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
            format_func=lambda x: available_audio_models[x].display_html(),
            key="selected_audio_model",
            allow_none=False,
            disabled=not available_audio_models
            or not gui.session_state.get("selected_models"),
        )

        render_fields(
            key="audio_inputs",
            available_models=available_audio_models,
            selected_models=[selected_audio_model],
            skip_fields=SKIP_AUDIO_INPUT_FIELDS,
        )


def merge_audio_and_video(
    filename: str,
    audio_url: str,
    video_url: str,
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

        return upload_file_from_bytes(
            filename,
            merged_video_bytes,
            "video/mp4",
        )
