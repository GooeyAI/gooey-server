import pytest

from daras_ai_v2 import embedding_model, settings
from daras_ai_v2.embedding_model import (
    EmbeddingInput,
    EmbeddingModels,
    _user_media_url_to_gs_uri,
    create_multimodal_embeddings,
)
from daras_ai_v2.exceptions import UserError

BUCKET = "gooey-test-bucket"
MEDIA = f"https://storage.googleapis.com/{BUCKET}/daras_ai/media"


@pytest.fixture(autouse=True)
def gcs_settings(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", BUCKET)
    monkeypatch.setattr(settings, "GS_MEDIA_PATH", "daras_ai/media")


def test_accepts_file_uploaded_to_our_bucket():
    assert (
        _user_media_url_to_gs_uri(f"{MEDIA}/6b1f0c4e/cat.png")
        == f"gs://{BUCKET}/daras_ai/media/6b1f0c4e/cat.png"
    )


@pytest.mark.parametrize(
    "url",
    [
        # any host: gs_url_to_uri drops it, so the path alone would pick the bucket
        "https://evil.example/other-bucket/secret.pdf",
        # a host that isn't ours, mimicking our own bucket path
        f"https://evil.example/{BUCKET}/daras_ai/media/6b1f0c4e/cat.png",
        # the right host, someone else's bucket
        "https://storage.googleapis.com/other-bucket/daras_ai/media/6b1f0c4e/secret.pdf",
        # our bucket, but outside the user media prefix
        f"https://storage.googleapis.com/{BUCKET}/static/index.html",
        # the prefix alone, naming no file
        MEDIA,
        # our prefix smuggled into the query string
        f"https://evil.example/other-bucket/x.png?storage.googleapis.com/{BUCKET}/daras_ai/media",
        # plain http
        f"http://storage.googleapis.com/{BUCKET}/daras_ai/media/6b1f0c4e/cat.png",
        # climbing out of the prefix, literally and percent-encoded
        f"{MEDIA}/../../static/index.html",
        f"{MEDIA}/..%2F..%2Fstatic/index.html",
        f"{MEDIA}/6b1f0c4e%2F..%2F..%2F..%2Fother/x.png",
    ],
)
def test_rejects_urls_outside_our_media_prefix(url):
    with pytest.raises(UserError):
        _user_media_url_to_gs_uri(url)


def test_rejects_everything_when_no_bucket_is_configured(monkeypatch):
    # local dev stores uploads on disk, which vertex can't read anyway
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    with pytest.raises(UserError):
        _user_media_url_to_gs_uri(f"{MEDIA}/6b1f0c4e/cat.png")


def test_rejected_url_never_reaches_vertex(monkeypatch):
    def fail(**kwargs):
        raise AssertionError("vertex was called with an unvalidated url")

    monkeypatch.setattr(embedding_model, "_run_vertex_embedding", fail)
    with pytest.raises(UserError):
        create_multimodal_embeddings(
            [
                EmbeddingInput(text="a cat"),
                EmbeddingInput(url="https://evil.example/other-bucket/secret.pdf"),
            ],
            EmbeddingModels.gemini_embedding_2,
        )
