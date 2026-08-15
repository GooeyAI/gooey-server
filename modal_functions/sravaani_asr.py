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

MODEL_ID = "ARTPARK-IISc/SraVaani-1.0"

cache_dir = "/cache"
model_cache = modal.Volume.from_name("hf-model-cache", create_if_missing=True)

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
    )
    .env(
        {
            "HF_HUB_CACHE": cache_dir,
            "HF_TOKEN": config("HF_TOKEN", ""),
            "HF_XET_HIGH_PERFORMANCE": "1",
        }
    )
)


def load_model(model_id: str):
    """Load the SraVaani ASR model via transformers remote code."""
    import torch
    from transformers import AutoModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading model: {model_id} on {device}")
    model = (
        AutoModel.from_pretrained(model_id, trust_remote_code=True).to(device).eval()
    )
    print("Model loaded successfully")

    return model


@app.cls(
    image=image,
    gpu="a10g",
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
        self.model = load_model(MODEL_ID)

    @modal.method()
    def run(self, audio_url: str) -> str:
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
            transcriptions = self.model.transcribe([audio_path])
            transcription = transcriptions[0]
            print(f"Transcription: {transcription}")

            return transcription

        finally:
            # Clean up temporary file
            if os.path.exists(audio_path):
                os.remove(audio_path)


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
