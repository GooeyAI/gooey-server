"""
To deploy changes to remote functions, run this file directly as a script:

```bash
poetry run python modal_functions/meta_omnilingual_asr.py
```

Or use the modal CLI:

```bash
poetry run modal deploy modal_functions/meta_omnilingual_asr.py
```
"""

import modal


app = modal.App("gooey-meta-omnilingual-asr")

cache_dir = "/cache"
model_cache = modal.Volume.from_name("omnilingual-asr-cache", create_if_missing=True)

# Create Modal image with required dependencies
image = (
    modal.Image.debian_slim()
    .apt_install("libsndfile1")  # Required for audio processing
    .pip_install(
        "omnilingual-asr",
        "requests~=2.31",
    )
    .env({"FAIRSEQ2_CACHE_DIR": cache_dir, "HF_XET_HIGH_PERFORMANCE": "1"})
)


def load_pipeline(model_card: str):
    """Load the ASR inference pipeline."""
    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

    print(f"Loading model: {model_card}")
    pipeline = ASRInferencePipeline(model_card=model_card, device="cuda")
    print("Model loaded successfully")

    return pipeline


@app.cls(
    image=image,
    gpu="a10g",
    volumes={cache_dir: model_cache},
    timeout=30 * 60,
    scaledown_window=90,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
class Omnilingual:
    @modal.enter(snap=True)
    def load(self):
        self.model = load_pipeline("omniASR_LLM_7B")

    @modal.method()
    def run(self, audio_url: str, language: str | None = None) -> str:
        """Run transcription on the given audio file."""
        import os

        # Download audio file
        print(f"Downloading audio from: {audio_url}")
        audio_path = download_audio(audio_url)

        try:
            # Run transcription
            if language:
                print(f"Transcribing audio in language: {language}")
            else:
                print("Transcribing audio with language auto-detection")
            transcriptions = self.model.transcribe(
                [audio_path], lang=[language], batch_size=1
            )

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
