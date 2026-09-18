import typing

from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import embeddings_model_selector
from daras_ai_v2.embedding_model import (
    EmbeddingInput,
    EmbeddingModels,
    create_embeddings,
    create_multimodal_embeddings,
)
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.pydantic_validation import HttpUrlStr


class EmbeddingsPage(BasePage):
    title = "Embeddings"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aeb83ee8-889e-11ee-93dc-02420a000143/Youtube%20transcripts%20GPT%20extractions.png.png"
    workflow = Workflow.EMBEDDINGS
    slug_versions = ["embeddings", "embed", "text-embedings"]
    price = 1

    class RequestModel(BasePage.RequestModel):
        # optional so that a multimodal run can send media and no text at all. Callers
        # that only ever send texts are unaffected.
        texts: list[str] | None = None

        # only read by models with supports_multimodal set
        input_images: list[HttpUrlStr] | None = None
        input_audio: list[HttpUrlStr] | None = None
        input_videos: list[HttpUrlStr] | None = None
        input_documents: list[HttpUrlStr] | None = None

        selected_model: (
            typing.Literal[tuple(e.name for e in EmbeddingModels)] | None
        ) = None

    class ResponseModel(BaseModel):
        # one vector per input, ordered texts -> images -> audio -> videos -> documents
        embeddings: list[list[float]]

    def render_form_v2(self):
        col1, col2 = gui.columns(2)
        with col1:
            embeddings_model_selector(key="selected_model")

        texts = gui.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            col1, col2 = gui.columns([8, 3], responsive=False)
            with col1:
                texts[i] = gui.text_area(f"##### `texts[{i}]`", value=text)
            with col2:
                if gui.button("🗑️", className="mt-5"):
                    texts.pop(i)
                    gui.rerun()
        if gui.button("➕ Add"):
            texts.append("")
            gui.rerun()

        model = EmbeddingModels.get(gui.session_state.get("selected_model"))
        if model and model.supports_multimodal:
            self.render_media_inputs(model)
        else:
            for key in MEDIA_FIELDS:
                gui.session_state.pop(key, None)

    def render_media_inputs(self, model: EmbeddingModels):
        gui.write("---")
        gui.caption(
            f"{model.label} embeds media into the same vector space as text, "
            "so anything uploaded here can be compared directly against a text query. "
            "Each input gets its own embedding."
        )

        if model.max_images:
            gui.file_uploader(
                label=f"##### 🏞️ Images\nUp to {model.max_images} per run.",
                key="input_images",
                accept=["image/*"],
                accept_multiple_files=True,
            )
        if model.max_audio_seconds:
            gui.file_uploader(
                label=f"##### 🎵 Audio\nUp to {model.max_audio_seconds}s each.",
                key="input_audio",
                accept=["audio/*"],
                accept_multiple_files=True,
            )
        if model.max_video_seconds:
            gui.file_uploader(
                label=f"##### 🎥 Video\nUp to {model.max_video_seconds}s each.",
                key="input_videos",
                accept=["video/*"],
                accept_multiple_files=True,
            )
        if model.max_documents:
            gui.file_uploader(
                label=(
                    f"##### 📄 Documents\nUp to {model.max_documents} PDF "
                    f"of {model.max_document_pages} pages."
                ),
                key="input_documents",
                accept=[".pdf"],
                accept_multiple_files=model.max_documents > 1,
            )

    def render_output(self):
        labels = embedding_input_labels(gui.session_state)
        for i, embedding in enumerate(gui.session_state.get("embeddings", [])):
            try:
                gui.write(f"##### `embeddings[{i}]` · {labels[i]}")
            except IndexError:
                gui.write(f"##### `embeddings[{i}]`")
            gui.json(embedding, depth=0)

    def render_run_preview_output(self, state: dict):
        texts = gui.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            texts[i] = gui.text_area(f"`texts[{i}]`", value=text, disabled=True)
        for key in MEDIA_FIELDS:
            for url in state.get(key) or []:
                gui.write(url)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: EmbeddingsPage.RequestModel = self.RequestModel.model_validate(state)
        model = EmbeddingModels[request.selected_model]

        inputs = collect_embedding_inputs(request, model)
        if not inputs:
            raise UserError("Please provide at least one text or file to embed.")

        if any(inp.url for inp in inputs):
            embeddings = create_multimodal_embeddings(inputs, model)
        else:
            # keep the plain text path untouched, so every other model behaves as before
            embeddings = create_embeddings([inp.text for inp in inputs], model)

        state["embeddings"] = embeddings.tolist()
        yield


# request fields holding media urls, in the order their embeddings are returned
MEDIA_FIELDS = ["input_images", "input_audio", "input_videos", "input_documents"]

# media fields we can cap by count. Audio and video are capped by duration instead,
# which we can't check without probing the file, so those are surfaced as help text.
MEDIA_COUNT_LIMITS = {
    "input_images": ("max_images", "images"),
    "input_documents": ("max_documents", "documents"),
}


def collect_embedding_inputs(
    request: EmbeddingsPage.RequestModel, model: EmbeddingModels
) -> list[EmbeddingInput]:
    inputs = [
        EmbeddingInput(text=text)
        for text in (request.texts or [])
        if text and text.strip()
    ]
    if not model.supports_multimodal:
        return inputs

    for key in MEDIA_FIELDS:
        urls = getattr(request, key) or []
        if not urls:
            continue
        try:
            attr, noun = MEDIA_COUNT_LIMITS[key]
        except KeyError:
            pass
        else:
            limit = getattr(model, attr)
            if len(urls) > limit:
                raise UserError(
                    f"{model.label} accepts at most {limit} {noun} per run, got {len(urls)}."
                )
        inputs += [EmbeddingInput(url=url) for url in urls]

    return inputs


def embedding_input_labels(state: dict) -> list[str]:
    labels = [
        f"`texts[{i}]`"
        for i, text in enumerate(state.get("texts") or [])
        if text and text.strip()
    ]
    for key in MEDIA_FIELDS:
        labels += [url.rsplit("/", 1)[-1] for url in state.get(key) or []]
    return labels
