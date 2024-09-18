import typing

from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import embeddings_model_selector
from daras_ai_v2.embedding_model import (
    EmbeddingModels,
    create_embeddings,
)


class EmbeddingsPage(BasePage):
    title = "Embeddings"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aeb83ee8-889e-11ee-93dc-02420a000143/Youtube%20transcripts%20GPT%20extractions.png.png"
    workflow = Workflow.EMBEDDINGS
    slug_versions = ["embeddings", "embed", "text-embedings"]
    sdk_method_name = "embed"
    price = 1

    class RequestModel(BasePage.RequestModel):
        texts: list[str]
        selected_model: EmbeddingModels.api_enum | None

    class ResponseModel(BaseModel):
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

    def render_output(self):
        for i, embedding in enumerate(gui.session_state.get("embeddings", [])):
            gui.write(f"##### `embeddings[{i}]`")
            gui.json(embedding, depth=0)

    def render_example(self, state: dict):
        texts = gui.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            texts[i] = gui.text_area(f"`texts[{i}]`", value=text, disabled=True)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: EmbeddingsPage.RequestModel = self.RequestModel.parse_obj(state)
        model = EmbeddingModels[request.selected_model]
        state["embeddings"] = create_embeddings(request.texts, model).tolist()
        yield
