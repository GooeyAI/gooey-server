import pytest

import gooey_gui as gui
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.exceptions import UserError
from recipes.embeddings_page import (
    MAX_MULTIMODAL_INPUTS_PER_RUN,
    MEDIA_FIELDS,
    EmbeddingsPage,
    collect_embedding_inputs,
)

GEMINI = EmbeddingModels.gemini_embedding_2
OPENAI = EmbeddingModels.openai_3_large
MEDIA = "https://storage.googleapis.com/gooey-test-bucket/daras_ai/media"


def collect(model: EmbeddingModels, **fields):
    request = EmbeddingsPage.RequestModel(selected_model=model.name, **fields)
    return collect_embedding_inputs(request, model)


def test_every_media_uploader_stores_a_list(monkeypatch):
    # a single-file uploader stores a bare url, which RequestModel's list fields reject,
    # so a one-pdf upload would fail before embedding anything
    uploaders = {}
    monkeypatch.setattr(
        gui, "file_uploader", lambda **kwargs: uploaders.update({kwargs["key"]: kwargs})
    )
    monkeypatch.setattr(gui, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui, "caption", lambda *args, **kwargs: None)

    EmbeddingsPage.render_media_inputs(None, GEMINI)

    assert set(uploaders) == set(MEDIA_FIELDS)
    assert all(kwargs["accept_multiple_files"] for kwargs in uploaders.values())


@pytest.mark.parametrize("model", [GEMINI, OPENAI])
def test_blank_text_among_real_ones_is_rejected_not_dropped(model):
    # dropping texts[1] would put texts[2]'s vector at embeddings[1]
    with pytest.raises(UserError, match=r"texts\[1\]"):
        collect(model, texts=["a", "  ", "b"])


def test_all_blank_texts_mean_no_text():
    # the form starts with one empty box, which shouldn't block a media-only run
    inputs = collect(GEMINI, texts=[""], input_images=[f"{MEDIA}/u/cat.png"])
    assert [(inp.text, inp.url) for inp in inputs] == [(None, f"{MEDIA}/u/cat.png")]


def test_texts_keep_their_positions():
    inputs = collect(OPENAI, texts=["a", "b", "c"])
    assert [inp.text for inp in inputs] == ["a", "b", "c"]


@pytest.mark.parametrize("field", ["input_audio", "input_videos", "texts"])
def test_one_run_cannot_fan_out_past_the_cap(field):
    # audio and video have no count limit of their own, and neither do texts
    n = MAX_MULTIMODAL_INPUTS_PER_RUN + 1
    value = ["x"] * n if field == "texts" else [f"{MEDIA}/u/clip.mp3"] * n
    with pytest.raises(UserError, match="at most"):
        collect(GEMINI, **{field: value})


def test_cap_counts_every_kind_of_input_together():
    half = MAX_MULTIMODAL_INPUTS_PER_RUN // 2 + 1
    with pytest.raises(UserError, match="at most"):
        collect(
            GEMINI,
            texts=["x"] * half,
            input_videos=[f"{MEDIA}/u/clip.mp4"] * half,
        )


def test_cap_leaves_non_multimodal_models_alone():
    # these batch every text into one request, so the fan-out concern doesn't apply
    inputs = collect(OPENAI, texts=["x"] * (MAX_MULTIMODAL_INPUTS_PER_RUN + 1))
    assert len(inputs) == MAX_MULTIMODAL_INPUTS_PER_RUN + 1
