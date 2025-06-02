import io
import os
import typing
import zipfile
from contextlib import contextmanager
from enum import Enum

import gooey_gui as gui
import requests
from pydantic import BaseModel, Field

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun, Workflow
from daras_ai.image_input import (
    gcs_blob_for,
    upload_gcs_blob_from_bytes,
)
from daras_ai_v2 import icons
from daras_ai_v2.base import BasePage
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.doc_search_settings_widgets import bulk_documents_uploader
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.fal_ai import generate_on_fal
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.stable_diffusion import LoraWeight, Text2ImgModels
from recipes.CompareText2Img import CompareText2ImgPage
from workspaces.models import Workspace

# eco cost
WATER_CUPS_PER_STEP = 0.01177967574
ELECTRICITY_PER_STEP = 0.005782746854


class FluxLoraModelTypes(Enum):
    concept = "🍎 Concept (Objects, Characters, Clothing, Anatomy, Poses, etc.)"
    style = "🎨 Style (A time period, Art style, or General aesthetic)"


class FluxLoraInputsBase(BaseModel):
    input_images: list[str] = Field(
        [],
        title="Input Images",
        description="Upload a few images of a consistent style, concept or character.\n\n"
        "Try to use at least 5-10 images, although more is better.",
    )
    trigger_word: str | None = Field(
        None,
        title="Trigger Word",
        description="(optional) Trigger word to be used in the prompt.\n\n"
        "If not provided, a trigger word will not be used. "
        "If captions are provided, the trigger word will be used to replace the `[trigger]` keyword in the captions.",
    )
    captions: dict[str, str] | None = Field(
        None,
        title="Captions",
        description="(optional) Captions for the images.\n\n"
        "The captions can include a special keyword `[trigger]`. If a Trigger Word is specified, it will replace [trigger] in the captions.",
    )


class FluxLoraFastInputs(FluxLoraInputsBase):
    model_type: typing.Literal[tuple(e.name for e in FluxLoraModelTypes)] | None = (
        Field(
            None,
            title="Model Type",
            description="The type of model to train.\n\n"
            'Choose "style" if you want to train a model to generate images in a specific style.\n'
            'Choose "concept" if you want to train a model to generate images based on a concept or character.',
        )
    )


class FinetuneModel(typing.NamedTuple):
    label: str
    inputs_schema: typing.Type[BaseModel]
    model_id: str


class FinetuneModels(FinetuneModel, Enum):
    flux_lora_fast = FinetuneModel(
        label="Flux Lora Fast (blackforestlabs.ai)",
        inputs_schema=FluxLoraFastInputs,
        model_id="fal-ai/flux-lora-fast-training",
    )
    flux_lora_portrait = FinetuneModel(
        label="Flux Lora Portrait (blackforestlabs.ai)",
        inputs_schema=FluxLoraInputsBase,
        model_id="fal-ai/flux-lora-portrait-trainer",
    )


class ModelTrainerPage(BasePage):
    title = "Model Trainer"
    workflow = Workflow.MODEL_TRAINER
    slug_versions = ["model-trainer", "train", "lora", "model-trainer"]

    class RequestModel(BasePage.RequestModel):
        selected_model: typing.Literal[tuple(e.name for e in FinetuneModels)] | None = (
            Field(None, title="Model")
        )

        inputs: FluxLoraFastInputs

        learning_rate: float | None = Field(
            0.00009,
            title="Learning Rate",
            description="The learning rate to use for training the model.",
        )
        steps: int | None = Field(
            1000,
            title="Steps",
            description="The number of steps to train the model for.",
        )

    class ResponseModel(BaseModel):
        model_url: str = Field(description="URL to the trained model.")

    def run_v2(
        self,
        request: "ModelTrainerPage.RequestModel",
        response: "ModelTrainerPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        model = FinetuneModels[request.selected_model]
        yield f"Training {model.label}..."

        match model:
            case FinetuneModels.flux_lora_fast:
                with zip_images(
                    request.inputs.input_images, request.inputs.captions
                ) as images_data_url:
                    result = yield from generate_on_fal(
                        model.model_id,
                        dict(
                            images_data_url=images_data_url,
                            trigger_word=request.inputs.trigger_word,
                            is_style=(
                                request.inputs.model_type
                                == FluxLoraModelTypes.style.name
                            ),
                            steps=request.steps,
                        ),
                    )
                response.model_url = result["diffusers_lora_file"]["url"]

            case FinetuneModels.flux_lora_portrait:
                with zip_images(
                    request.inputs.input_images, request.inputs.captions
                ) as images_data_url:
                    result = yield from generate_on_fal(
                        model.model_id,
                        dict(
                            images_data_url=images_data_url,
                            trigger_phrase=request.inputs.trigger_word,
                            steps=request.steps,
                            learning_rate=request.learning_rate,
                        ),
                    )
                response.model_url = result["diffusers_lora_file"]["url"]

    def render_form_v2(self):
        selected_model = enum_selector(
            enum_cls=FinetuneModels,
            label=f"###### {ModelTrainerIcons.model} {field_title(self.RequestModel, 'selected_model')}",
            key="selected_model",
            use_selectbox=True,
        )

        match selected_model:
            case (
                FinetuneModels.flux_lora_fast.name
                | FinetuneModels.flux_lora_portrait.name
            ):
                render_flux_lora_fast_form(selected_model)

    def render_settings(self):
        gui.number_input(
            label=f"###### {ModelTrainerIcons.learning_rate} {field_title(self.RequestModel, 'learning_rate')}",
            key="learning_rate",
            help=field_desc(self.RequestModel, "learning_rate"),
        )
        gui.slider(
            label=f"###### {ModelTrainerIcons.steps} {field_title(self.RequestModel, 'steps')}",
            key="steps",
            help=field_desc(self.RequestModel, "steps"),
            min_value=1,
            step=50,
            max_value=10000,
        )

    def get_terms_caption(self):
        terms_caption = super().get_terms_caption()
        terms_caption += " You also confirm that you have ownership IP rights to all uploaded images."

        return terms_caption

    def get_cost_note(self) -> str | None:
        steps = gui.session_state.get("steps") or 1
        return f"*{steps} steps @ 0.36 Cr /step*"

    # Number of lines to clamp the run cost notes to
    run_cost_line_clamp: int = 3

    def additional_notes(self) -> str | None:
        """Return additional notes to display."""
        steps = gui.session_state.get("steps") or 1
        return (
            f"🌳 [Eco Cost](https://gooey.ai/energy): "
            f"🚰 ~{int(steps * WATER_CUPS_PER_STEP)} cups of water "
            f"& ⚡ electricity to power an EU household for ~{int(steps * ELECTRICITY_PER_STEP)} min."
        )

    def get_raw_price(self, state: dict) -> float:
        return 0.36 * (state.get("steps") or 1)

    def render_output(self):
        model_url = gui.session_state.get("model_url")
        if not model_url:
            return
        gui.success(
            "The model has been trained! "
            "You can now use it to generate images on Gooey or download the model to run it locally.",
            icon="🎉",
        )

        if gui.button(f"{icons.run} Generate Image", type="primary"):
            sr = call_text2img_for_model(
                self.request.user, self.current_workspace, model_url
            )
            raise gui.RedirectException(sr.get_app_url())

        run_cost = CompareText2ImgPage(request=self.request).get_price_roundoff(
            gui.session_state
        )
        gui.caption(f"(Run cost for Image Generation = {run_cost} credits)")

        copy_to_clipboard_button(
            label=f"{icons.copy_solid} Copy Model URL",
            value=model_url,
            type="secondary",
        )
        with (
            gui.tag("a", href=model_url),
            gui.tag("button", className="btn btn-theme btn-secondary", type="button"),
        ):
            gui.html(f"{icons.download_solid} Download Model")

    @classmethod
    def get_run_title(cls, sr: SavedRun, pr: PublishedRun) -> str:
        inputs = sr.state.get("inputs") or {}
        trigger_word = inputs.get("trigger_word")
        title = super().get_run_title(sr, pr)
        return " ".join(filter(None, [trigger_word, title]))


def call_text2img_for_model(
    current_user: AppUser, workspace: Workspace, model_url: str
) -> SavedRun:
    from routers.api import submit_api_call

    inputs = gui.session_state.get("inputs") or {}
    trigger_word = inputs.get("trigger_word")
    captions = inputs.get("captions")
    if trigger_word:
        text_prompt = trigger_word
    elif captions:
        text_prompt = next(iter(captions.values()))
    elif (
        inputs.get("model_type") == FluxLoraModelTypes.style.name
        and gui.session_state.get("selected_model")
        == FinetuneModels.flux_lora_fast.name
    ):
        text_prompt = "tropical beach boulevard"
    else:
        text_prompt = "a person"
    sr = submit_api_call(
        page_cls=CompareText2ImgPage,
        query_params={},
        current_user=current_user,
        workspace=workspace,
        request_body=CompareText2ImgPage.RequestModel(
            loras=[LoraWeight(path=model_url)],
            text_prompt=text_prompt,
            selected_models=[Text2ImgModels.flux_1_dev.name],
            quality=50,
        ).model_dump(exclude_unset=True),
    )[1]
    return sr


@contextmanager
def zip_images(input_images: list[str], captions: dict[str, str] | None) -> str:
    f = io.BytesIO()
    with zipfile.ZipFile(f, "w") as zipf:
        for i, image in enumerate(input_images):
            r = requests.get(image)
            raise_for_status(r, is_user_url=True)
            ext = os.path.splitext(image)[1]
            zipf.writestr(f"image_{i}{ext}", r.content)
            try:
                caption = captions[image]
            except (TypeError, KeyError):
                pass
            else:
                zipf.writestr(f"image_{i}.txt", caption)
    blob = gcs_blob_for("images.zip")
    try:
        upload_gcs_blob_from_bytes(blob, f.getvalue(), "application/zip")
        yield blob.public_url
    finally:
        blob.delete()


def render_flux_lora_fast_form(selected_model: str):
    inputs = FluxLoraFastInputs.model_validate(gui.session_state.get("inputs", {}))
    gui.session_state.setdefault("inputs.input_images", inputs.input_images)
    inputs.input_images = bulk_documents_uploader(
        label=f"###### {ModelTrainerIcons.input_images} {field_title(FluxLoraFastInputs, 'input_images')}",
        key="inputs.input_images",
        help=field_desc(FluxLoraFastInputs, "input_images"),
        accept=["image/*"],
    )
    if selected_model == FinetuneModels.flux_lora_fast.name:
        inputs.model_type = enum_selector(
            enum_cls=FluxLoraModelTypes,
            label=f"###### {ModelTrainerIcons.model_type} {field_title(FluxLoraFastInputs, 'model_type')}",
            value=inputs.model_type and inputs.model_type,
            use_selectbox=True,
            help=field_desc(FluxLoraFastInputs, "model_type"),
        )
    inputs.trigger_word = gui.text_input(
        label=f"{ModelTrainerIcons.trigger_word} {field_title(FluxLoraFastInputs, 'trigger_word')}",
        value=inputs.trigger_word,
        help=field_desc(FluxLoraFastInputs, "trigger_word"),
    )
    if inputs.input_images and inputs.model_type != FluxLoraModelTypes.style.name:
        inputs.captions = render_captions(inputs)
    gui.session_state["inputs"] = inputs.model_dump()


def render_captions(inputs: FluxLoraFastInputs, key: str = "captions"):
    captions = inputs.captions or {}

    with gui.div(className="gui-input"):
        with gui.tag("label"):
            gui.write(
                f"{ModelTrainerIcons.captions} {field_title(FluxLoraFastInputs, key)}",
                help=field_desc(FluxLoraFastInputs, key),
                unsafe_allow_html=True,
            )
        with (
            gui.styled(CAPTIONS_SECTION_STYLE),
            gui.div(className="d-flex flex-wrap gap-3 p-1 overflow-auto"),
        ):
            for image in inputs.input_images:
                with gui.div(className="d-flex d-md-block gap-3 w-md-100"):
                    gui.image(image)
                    captions[image] = gui.text_input(
                        label="", value=captions.get(image), key=f"{key} => {image}"
                    )

    captions = {k: v for k, v in captions.items() if v}
    if captions:
        return captions
    else:
        return None


class ModelTrainerIcons:
    model = '<i class="fa-sharp fa-regular fa-brain-circuit"></i>'
    learning_rate = '<i class="fa-sharp fa-regular fa-lines-leaning"></i>'
    steps = '<i class="fa-sharp fa-regular fa-arrow-progress"></i>'
    input_images = '<i class="fa-sharp fa-regular fa-images"></i>'
    model_type = '<i class="fa-sharp fa-regular fa-swatchbook"></i>'
    trigger_word = '<i class="fa-sharp fa-regular fa-raygun"></i>'
    captions = '<i class="fa-sharp fa-regular fa-closed-captioning"></i>'


CAPTIONS_SECTION_STYLE = """
& {
    max-height: 30vh;
}
& img {
    height: 200px;
    width: 200px;
    object-fit: cover;
    border-radius: 3px;
    box-shadow: 0 0 3px rgba(0, 0, 0, 0.2);
}
@media (max-width: 768px) {
    & .gui-input-text {
        width: 100%;
    }
    & img {
        width: 50px;
        height: auto;
    }
    .w-md-100 {
        width: 100%;
    }
}
"""
