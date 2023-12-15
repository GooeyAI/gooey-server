import typing

from django.db import models
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.gpu_server import call_celery_task


class EmbeddingModels(models.TextChoices):
    e5_large_v2 = (
        "E5 large v2 (Liang Wang)",
        "intfloat/e5-large-v2",
    )
    e5_base_v2 = (
        "E5 base v2 (Liang Wang)",
        "intfloat/e5-base-v2",
    )
    multilingual_e5_base = (
        "Multilingual E5 Base (Liang Wang)",
        "intfloat/multilingual-e5-base",
    )
    multilingual_e5_large = (
        "Multilingual E5 Large (Liang Wang)",
        "intfloat/multilingual-e5-large",
    )
    gte_large = (
        "General Text Embeddings Large (Dingkun Long)",
        "thenlper/gte-large",
    )
    gte_base = (
        "General Text Embeddings Base (Dingkun Long)",
        "thenlper/gte-base",
    )


class EmbeddingsPage(BasePage):
    title = "Embeddings"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aeb83ee8-889e-11ee-93dc-02420a000143/Youtube%20transcripts%20GPT%20extractions.png.png"
    workflow = Workflow.EMBEDDINGS
    slug_versions = ["embeddings", "embed", "text-embedings"]
    price = 1

    class RequestModel(BaseModel):
        texts: list[str]
        selected_model: typing.Literal[tuple(e.name for e in EmbeddingModels)] | None

    class ResponseModel(BaseModel):
        embeddings: list[list[float]]

    def render_form_v2(self):
        col1, col2 = st.columns(2)
        with col1:
            enum_selector(
                EmbeddingModels,
                label="##### Embeddings Model",
                key="selected_model",
                use_selectbox=True,
            )

        texts = st.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            col1, col2 = st.columns([8, 3], responsive=False)
            with col1:
                texts[i] = st.text_area(f"##### `texts[{i}]`", value=text)
            with col2:
                if st.button("🗑️", className="mt-5"):
                    texts.pop(i)
                    st.experimental_rerun()
        if st.button("➕ Add"):
            texts.append("")
            st.experimental_rerun()

    def render_output(self):
        for i, embedding in enumerate(st.session_state.get("embeddings", [])):
            st.write(f"##### `embeddings[{i}]`")
            st.json(embedding, depth=0)

    def render_example(self, state: dict):
        texts = st.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            texts[i] = st.text_area(f"`texts[{i}]`", value=text, disabled=True)

    # def fields_to_save(self) -> [str]:
    #     to_save = super().fields_to_save()
    #     # dont save the embeddings they are too big + firebase doesn't support 2d array
    #     to_save.remove("embeddings")
    #     return to_save

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: EmbeddingsPage.RequestModel = self.RequestModel.parse_obj(state)
        model = EmbeddingModels[request.selected_model]
        state["embeddings"] = call_celery_task(
            "text_embeddings",
            pipeline={"model_id": model.label},
            inputs={"texts": request.texts},
        )
        yield
