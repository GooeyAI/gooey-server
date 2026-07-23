from __future__ import annotations

import html
import typing

import gooey_gui as gui
from pydantic import BaseModel
from requests.utils import CaseInsensitiveDict

from ai_models.llm_openapi import ImageModelMarker
from ai_models.models import AIModelSpec
from bots.models import Workflow
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.base import BasePage
from daras_ai_v2.exceptions import PaymentRequired, UserError
from daras_ai_v2.fal_ai import format_pricing_notes, generate_on_fal
from daras_ai_v2.preview_img import media_preview_img
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.safety_checker import SAFETY_CHECKER_MSG, safety_checker
from daras_ai_v2.schema_model_form import (
    build_combined_input_schema,
    render_fields,
)
from daras_ai_v2.variables_widget import render_prompt_vars
from usage_costs.models import ModelSku


class ImageGenPage(BasePage):
    title = Workflow.IMAGE_GEN.label
    workflow = Workflow.IMAGE_GEN
    slug_versions = ["image-generation", "image-gen"]
    price_deferred = True

    class RequestModel(BasePage.RequestModel):
        selected_model: ImageModelMarker | None = None
        inputs: dict[str, typing.Any] | None = None

    class ResponseModel(BaseModel):
        output_images: dict[str, list[HttpUrlStr]]

    def run_v2(
        self, request: ImageGenPage.RequestModel, response: ImageGenPage.ResponseModel
    ) -> typing.Iterator[str | None]:
        if not request.selected_model:
            raise UserError("Please select a model")
        inputs = request.inputs or {}
        yield from self.run_safety_checker(inputs)
        model = self.get_model(request.selected_model)
        self.validate_model_inputs(model, inputs)
        if model.paid_only and not self.current_workspace.is_paying:
            raise PaymentRequired([model.label])

        yield f"Running {model.label}"
        result = yield from generate_on_fal(
            model.model_id,
            inputs | dict(enable_safety_checker=False),
        )
        if not isinstance(result, dict):
            raise UserError(f"Invalid image output from {model.label}: {result}")
        if result.get("moderation_flagged"):
            raise UserError(SAFETY_CHECKER_MSG)
        image_urls = extract_generated_image_urls(result)
        if not image_urls:
            raise UserError(f"No image output from {model.label}: {result}")
        response.output_images = {model.name: image_urls}

    def get_model(self, model_name: str) -> AIModelSpec:
        try:
            return AIModelSpec.objects.get(
                category=AIModelSpec.Categories.image,
                name__iexact=model_name,
            )
        except AIModelSpec.DoesNotExist:
            available_models = AIModelSpec.objects.filter(
                category=AIModelSpec.Categories.image
            ).order_for_frontend()
            raise UserError(
                f"Model {model_name} not found. Should be one of: "
                + ", ".join(available_models.values_list("name", flat=True))
            )

    def run_safety_checker(self, inputs: dict) -> typing.Iterator[str | None]:
        if self.request.user.disable_safety_checker:
            return
        for key in ["prompt", "text_prompt", "negative_prompt"]:
            text = inputs.get(key)
            if not text:
                continue
            inputs[key] = render_prompt_vars(text, gui.session_state)
            yield "Running safety checker..."
            safety_checker(text=text)

    def validate_model_inputs(self, model: AIModelSpec, inputs: dict) -> None:
        input_schema = build_combined_input_schema([model])
        if not input_schema:
            raise UserError("The selected model does not have a usable request schema")
        missing_fields = [
            name
            for name in input_schema.get("required", [])
            if name not in inputs or inputs[name] is None or inputs[name] == ""
        ]
        if missing_fields:
            raise UserError(
                "Please provide: " + ", ".join(name.title() for name in missing_fields)
            )

    def render(self):
        image_models = list(
            AIModelSpec.objects.filter(
                category=AIModelSpec.Categories.image
            ).order_for_frontend(
                selected_models=gui.session_state.get("selected_model")
            )
        )
        self.available_models = CaseInsensitiveDict(
            {model.name: model for model in image_models}
        )
        super().render()

    def render_form_v2(self):
        selected_model = gui.session_state.get("selected_model")
        if not selected_model or selected_model not in self.available_models:
            gui.session_state["selected_model"] = None

        options = {
            name: model.display_html() for name, model in self.available_models.items()
        }
        selected_model = gui.selectbox(
            label="###### Image Model",
            options=list(options),
            format_func=options.__getitem__,
            key="selected_model",
        )
        render_fields(
            key="inputs",
            available_models=self.available_models,
            selected_models=[selected_model] if selected_model else [],
        )

    def validate_form_v2(self):
        selected_model = gui.session_state.get("selected_model")
        if not selected_model:
            raise UserError("Please select a model")
        self.validate_model_inputs(
            self.available_models[selected_model],
            gui.session_state.get("inputs") or {},
        )

    def render_output(self):
        self.render_run_preview_output(gui.session_state, preview=False)

    def render_run_preview_output(self, state: dict, preview: bool = True):
        selected_model = state.get("selected_model")
        image_urls = (state.get("output_images") or {}).get(selected_model, [])
        model = self.available_models.get(selected_model) if selected_model else None
        caption = model.label if model else selected_model
        for image_url in image_urls:
            gui.image(
                image_url,
                caption=caption,
                show_download_button=True,
                previewImg=media_preview_img(image_url) if preview else None,
            )

        prompt = get_prompt(state.get("inputs") or {})
        if preview and prompt:
            prompt_preview = truncate_text_words(html.escape(prompt), 200)
            gui.write(
                '<i class="fa-regular fa-lightbulb-on" '
                'style="fontSize: 0.8rem; vertical-align: 0.05rem"></i>'
                f"&nbsp;{prompt_preview}",
                unsafe_allow_html=True,
            )

    def get_raw_price(self, state: dict) -> float:
        return self.get_total_linked_usage_cost_in_credits(default=1000)

    def additional_notes(self) -> str | None:
        model_name = gui.session_state.get("selected_model")
        if not model_name:
            return None
        model = self.available_models.get(model_name)
        if not model:
            return None
        return format_pricing_notes(
            {model.model_id: model.label},
            sku=ModelSku.fal_billable_units,
        )

    def related_workflows(self) -> list:
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.Img2Img import Img2ImgPage
        from recipes.VideoGenPage import VideoGenPage

        return [CompareText2ImgPage, Img2ImgPage, VideoGenPage]

    @classmethod
    def preview_input(cls, state: dict) -> str | None:
        return get_prompt(state.get("inputs") or {}) or super().preview_input(state)

    @classmethod
    def get_tool_call_schema(cls, state: dict) -> dict[str, typing.Any]:
        properties = super().get_tool_call_schema(state)
        selected_model = state.get("selected_model")
        image_models = AIModelSpec.objects.filter(
            category=AIModelSpec.Categories.image,
            name=selected_model,
        )
        if inputs_schema := build_combined_input_schema(image_models):
            properties["inputs"] = inputs_schema
            properties.pop("selected_model", None)
        else:
            properties.pop("inputs", None)
        return properties


def extract_generated_image_urls(result: dict) -> list[str]:
    urls = []
    for key in ["images", "image", "output", "outputs"]:
        if key in result:
            urls.extend(extract_asset_urls(result[key]))
    return list(dict.fromkeys(urls))


def extract_asset_urls(value: typing.Any) -> list[str]:
    match value:
        case str() if value.startswith(("http://", "https://")):
            return [value]
        case list():
            return [url for item in value for url in extract_asset_urls(item)]
        case dict() if isinstance(value.get("url"), str):
            return [value["url"]]
        case dict():
            return [
                url
                for key, item in value.items()
                if "image" in key.lower() or "output" in key.lower()
                for url in extract_asset_urls(item)
            ]
        case _:
            return []


def get_prompt(inputs: dict) -> str:
    return inputs.get("prompt") or inputs.get("text_prompt") or ""
