"""
To deploy changes to remote functions, run this file directly as a script:

```bash
poetry run python modal_functions/sravaani_asr.py
```

Or use the modal CLI:

```bash
poetry run modal deploy modal_functions/sravaani_asr.py
```

Note: the HuggingFace repo is gated, so a valid HF_TOKEN (with access granted to
ARTPARK-IISc/SraVaani-1.0) must be set in the environment when deploying.
"""

import modal
from decouple import config

app = modal.App("gooey-sravaani-asr")

SRAVAANI_MODEL_ID = "ARTPARK-IISc/SraVaani-1.0"
SRAVAANI_MODEL_REVISION = "39c6add757f46af212d583ed765894ae78b2ebad"

cache_dir = "/cache"
model_cache = modal.Volume.from_name("hf-model-cache", create_if_missing=True)
hf_secret = modal.Secret.from_dict({"HF_TOKEN": config("HF_TOKEN", "")})

image = (
    modal.Image.debian_slim()
    .apt_install("libsndfile1")  # Required for audio processing
    .pip_install(
        "transformers~=5.15",
        "huggingface_hub[hf_transfer]",
        "torch~=2.13",
        "soundfile~=0.12",
        "sentencepiece~=0.2",
        "requests~=2.31",
        "python-decouple",
    )
    .env(
        {
            "HF_HUB_CACHE": cache_dir,
            "HF_XET_HIGH_PERFORMANCE": "1",
        }
    )
)


def load_model(model_id: str, revision: str):
    """Download and eagerly load a pinned SraVaani model snapshot."""
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading model: {model_id}@{revision} on {device}")
    model_path = snapshot_download(
        repo_id=model_id,
        revision=revision,
        cache_dir=cache_dir,
    )
    model = (
        AutoModel.from_pretrained(
            model_path,
            trust_remote_code=True,
            local_files_only=True,
        )
        .to(device)
        .eval()
    )
    model._ensure_loaded()
    print("Model loaded successfully")

    return model


@app.cls(
    image=image,
    gpu="a10g",
    secrets=[hf_secret],
    volumes={cache_dir: model_cache},
    timeout=30 * 60,
    scaledown_window=60 * 60,  # 1 hour
    max_containers=2,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
class SraVaani:
    @modal.enter(snap=True)
    def load(self):
        self.model = load_model(SRAVAANI_MODEL_ID, SRAVAANI_MODEL_REVISION)

    @modal.method()
    def run(self, audio_url: str, return_timestamps: bool = False) -> dict:
        """Run transcription on the given audio file.

        SraVaani identifies the spoken language automatically, so no language
        tag is needed at inference.
        """
        import os

        # Download audio file
        print(f"Downloading audio from: {audio_url}")
        audio_path = download_audio(audio_url)

        try:
            # Run transcription (language is auto-detected by the model)
            transcriptions = self.model.transcribe(
                [audio_path], timestamps=return_timestamps
            )
            transcription = _sravaani_transcription_to_output(
                transcriptions[0], return_timestamps=return_timestamps
            )
            print(f"Transcription: {transcription['text']}")

            return transcription

        finally:
            # Clean up temporary file
            if os.path.exists(audio_path):
                os.remove(audio_path)


def _sravaani_transcription_to_output(
    transcription, *, return_timestamps: bool
) -> dict:
    if not return_timestamps:
        return {"text": transcription}

    return {
        "text": transcription.text,
        "chunks": [
            {
                "timestamp": (word["start"], word["end"]),
                "text": word["word"],
                "speaker": None,
            }
            for word in transcription.timestamp["word"]
        ],
    }


def download_audio(url: str) -> str:
    """Download WAV audio file from URL to a temporary file."""
    import requests
    import tempfile
    import os

    response = requests.get(url, stream=True)
    response.raise_for_status()

    # Create temporary file with .wav extension
    fd, path = tempfile.mkstemp(suffix=".wav")

    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception:
        # Clean up on error
        if os.path.exists(path):
            os.remove(path)
        raise

    return path


if __name__ == "__main__":
    with modal.enable_output():
        app.deploy()
