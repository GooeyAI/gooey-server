import modal
from decouple import config

FAST_BOOT = True
MODEL_NAME = "AI71ai/agrillm-Qwen3-30B-A3B"
MODEL_REVISION = "b176600a65e75045bcae992161d839feb7d17a67"

VLLM_PORT = 8000
N_GPU = 2
MINUTES = 60  # seconds

app = modal.App("gooey-llm")

hf_cache_dir = "/cache"
vllm_cache_dir = "/vllm_cache"

model_cache = modal.Volume.from_name("hf-model-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install(
        "vllm==0.11.2",
        "huggingface-hub==0.36.0",
        "flashinfer-python==0.5.2",
        "python-decouple~=3.6",
    )
    .env(
        {
            "HF_XET_HIGH_PERFORMANCE": "1",
            "HF_HUB_CACHE": hf_cache_dir,
            "VLLM_CACHE_ROOT": vllm_cache_dir,
            "VLLM_API_KEY": config("MODAL_VLLM_API_KEY", ""),
        }
    )
)


@app.function(
    image=vllm_image,
    gpu=f"H100:{N_GPU}",
    scaledown_window=5 * MINUTES,
    timeout=3 * MINUTES,
    volumes={
        hf_cache_dir: model_cache,
        vllm_cache_dir: vllm_cache,
    },
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
    max_containers=1,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    import subprocess

    cmd = [
        "vllm",
        "serve",
        "--uvicorn-log-level=info",
        MODEL_NAME,
        "--revision",
        MODEL_REVISION,
        "--served-model-name",
        MODEL_NAME,
        "llm",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "hermes",
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
    ]

    cmd += ["--enforce-eager" if FAST_BOOT else "--no-enforce-eager"]

    cmd += ["--tensor-parallel-size", str(N_GPU)]

    print(cmd)

    subprocess.Popen(" ".join(cmd), shell=True)
