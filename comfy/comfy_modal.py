"""
Modal deployment for ComfyUI cloud (comfy.gooey.ai).

Each Gooey workspace gets its own ComfyUI sandbox with a persistent
`modal.Volume` mounted at /data (models, custom nodes, inputs, outputs), so
users build up their own model library per workspace.

Pre-bake the image (recommended before first launch, and after bumping
versions):

```bash
python comfy_modal.py  # runs a throwaway sandbox once to build+cache the image
```

The gateway (gateway/backends.py) imports `launch_sandbox()` to boot instances
on demand. Requires MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in the environment.
"""

import modal

APP_NAME = "gooey-comfyui"
COMFY_PORT = 8188
COMFY_VERSION = "0.3.44"

# GPU-seconds cap per sandbox — a hard backstop on runaway spend; the gateway's
# idle reaper normally stops sandboxes long before this
MAX_SANDBOX_LIFETIME = 12 * 60 * 60

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "wget", "libgl1", "libglib2.0-0")
    .pip_install("comfy-cli~=1.4")
    .run_commands(
        f"comfy --skip-prompt install --fast-deps --nvidia --version {COMFY_VERSION}"
    )
)


def launch_sandbox(
    workspace_id: int | str,
    gpu: str = "L4",
    timeout: int = MAX_SANDBOX_LIFETIME,
) -> modal.Sandbox:
    app = modal.App.lookup(APP_NAME, create_if_missing=True)
    volume = modal.Volume.from_name(
        f"comfyui-workspace-{workspace_id}", create_if_missing=True
    )
    return modal.Sandbox.create(
        "bash",
        "-c",
        # --base-directory keeps models/custom_nodes/input/output on the
        # workspace volume so they survive sandbox restarts
        f"mkdir -p /data/comfy && "
        f"comfy launch -- --listen 0.0.0.0 --port {COMFY_PORT} "
        f"--base-directory /data/comfy",
        app=app,
        image=image,
        gpu=gpu,
        timeout=timeout,
        encrypted_ports=[COMFY_PORT],
        volumes={"/data": volume},
    )


def sandbox_url(sandbox: modal.Sandbox) -> str:
    return sandbox.tunnels()[COMFY_PORT].url


if __name__ == "__main__":
    print("Building image by launching a throwaway sandbox ...")
    sb = launch_sandbox("image-build-test", timeout=5 * 60)
    print("Sandbox:", sb.object_id, "->", sandbox_url(sb))
    sb.terminate()
    print("Image built & cached. Done.")
