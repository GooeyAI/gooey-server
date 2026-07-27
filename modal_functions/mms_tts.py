"""
To deploy changes to remote functions, run this file directly as a script:

```bash
poetry run python modal_functions/mms_tts.py
```
"""

import modal
from decouple import config

app = modal.App("gooey-mms-tts-runner")

cache_dir = "/cache"
model_cache = modal.Volume.from_name("hf-model-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim()
    .pip_install(
        "transformers~=4.44",
        "huggingface_hub[hf_transfer]~=0.34.4",
        "torch~=2.5.1",
        "scipy~=1.11",
        "python-decouple~=3.6",
    )
    .env({"HF_HUB_CACHE": cache_dir, "HF_TOKEN": config("HF_TOKEN", cast=str)})
)


def load_pipe(language: str):
    import torch
    from transformers import pipeline

    has_cuda = torch.cuda.is_available()
    if has_cuda:
        print("Using GPU")
    else:
        print("GPU not available, using CPU")

    pipe = pipeline(
        "text-to-speech",
        model=f"facebook/mms-tts-{language}",
        tokenizer=f"facebook/mms-tts-{language}",
        device=0 if torch.cuda.is_available() else -1,
    )

    return pipe


@app.function(
    image=image,
    gpu="a10g",
    timeout=30 * 60,
    volumes={"/cache": model_cache},
    enable_memory_snapshot=True,
)
def run_mms_tts(language: str, text: str, upload_url: str):
    import torch

    pipe = load_pipe(language)

    print("Running inference")
    with torch.no_grad():
        output = pipe(text)

    upload_audio(output["audio"][0], upload_url, rate=output["sampling_rate"])


def upload_audio(audio, url: str, rate: int = 16_000):
    import scipy
    import io
    import numpy as np

    # Convert from pcm_f32le to pcm_s16le
    # Clip values to [-1.0, 1.0] range and scale to int16 range
    audio_clipped = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio_clipped * 32767).astype(np.int16)

    # The resulting audio output can be saved as a .wav file:
    f = io.BytesIO()
    scipy.io.wavfile.write(f, rate=rate, data=audio_int16)
    audio_bytes = f.getvalue()
    # upload to given url
    upload_audio_from_bytes(audio_bytes, url)


def upload_audio_from_bytes(audio: bytes, url: str):
    import requests

    r = requests.put(url, headers={"Content-Type": "audio/wav"}, data=audio)
    r.raise_for_status()


if __name__ == "__main__":
    with modal.enable_output():
        app.deploy()
