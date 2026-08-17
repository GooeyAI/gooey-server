"""
Manages one ComfyUI instance per Gooey workspace: launch on demand, meter GPU
time into Gooey credits every minute, and stop after a period of no traffic.
"""

import asyncio
import logging
import time

import httpx

from gateway import gooey_client, settings

logger = logging.getLogger("comfy.backends")

BILLING_INTERVAL = 60  # seconds; one billing tick = one GPU-minute


class ComfyInstance:
    def __init__(self, workspace_id: int, uid: str):
        self.workspace_id = workspace_id
        # the user who caused the launch; usage is billed to the workspace
        self.uid = uid
        self.instance_id: str = ""
        self.url: str = ""
        self.ready = False
        self.stopped = False
        self.stop_reason = ""
        self.started_at = time.time()
        self.last_active = time.time()
        self._tasks: list[asyncio.Task] = []

    def touch(self):
        self.last_active = time.time()


class BaseBackend:
    """One instance per workspace, lazily launched."""

    def __init__(self):
        self._instances: dict[int, ComfyInstance] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    async def get_or_launch(self, workspace_id: int, uid: str) -> ComfyInstance:
        lock = self._locks.setdefault(workspace_id, asyncio.Lock())
        async with lock:
            instance = self._instances.get(workspace_id)
            if instance and not instance.stopped:
                return instance

            balance = await gooey_client.get_balance(
                uid=uid, workspace_id=workspace_id
            )
            if balance < settings.MIN_CREDITS_TO_LAUNCH:
                raise gooey_client.InsufficientCredits(
                    f"This workspace needs at least "
                    f"{settings.MIN_CREDITS_TO_LAUNCH} credits to start ComfyUI."
                )

            instance = ComfyInstance(workspace_id, uid)
            self._instances[workspace_id] = instance
            await self._launch(instance)
            instance._tasks.append(asyncio.create_task(self._wait_ready(instance)))
            instance._tasks.append(asyncio.create_task(self._billing_loop(instance)))
            instance._tasks.append(asyncio.create_task(self._idle_reaper(instance)))
            return instance

    def get(self, workspace_id: int) -> ComfyInstance | None:
        instance = self._instances.get(workspace_id)
        if instance and not instance.stopped:
            return instance
        return None

    async def stop(self, workspace_id: int, reason: str = ""):
        instance = self._instances.pop(workspace_id, None)
        if not instance or instance.stopped:
            return
        instance.stopped = True
        instance.stop_reason = reason
        logger.info(f"stopping comfy instance for workspace {workspace_id}: {reason}")
        for task in instance._tasks:
            if task is not asyncio.current_task():
                task.cancel()
        await self._terminate(instance)

    async def shutdown(self):
        for workspace_id in list(self._instances):
            await self.stop(workspace_id, reason="gateway shutdown")

    async def _wait_ready(self, instance: ComfyInstance):
        async with httpx.AsyncClient(timeout=5) as client:
            for _ in range(120):
                if instance.stopped:
                    return
                try:
                    r = await client.get(instance.url + "/system_stats")
                    if r.status_code == 200:
                        instance.ready = True
                        logger.info(
                            f"comfy ready for workspace {instance.workspace_id}: "
                            f"{instance.url}"
                        )
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(5)
        await self.stop(instance.workspace_id, reason="ComfyUI failed to start")

    async def _billing_loop(self, instance: ComfyInstance):
        """Charge one GPU-minute per tick while the instance is up."""
        tick = 0
        while not instance.stopped:
            await asyncio.sleep(BILLING_INTERVAL)
            if instance.stopped or not self._is_billable(instance):
                continue
            tick += 1
            try:
                await gooey_client.record_usage(
                    uid=instance.uid,
                    workspace_id=instance.workspace_id,
                    gpu_ms=BILLING_INTERVAL * 1000,
                    # deterministic per tick: retries can never double-charge
                    invoice_id=f"{instance.instance_id}/{tick}",
                    note=f"ComfyUI GPU time ({settings.COMFY_BACKEND})",
                )
            except gooey_client.InsufficientCredits:
                await self.stop(
                    instance.workspace_id,
                    reason="Workspace ran out of credits. "
                    "Add credits on gooey.ai to continue.",
                )
                return
            except Exception as e:
                # transient billing-API failure: retry next tick with the same
                # invoice sequence rather than killing the user's session
                logger.exception(f"usage recording failed (tick {tick}): {e}")

    async def _idle_reaper(self, instance: ComfyInstance):
        while not instance.stopped:
            await asyncio.sleep(30)
            idle = time.time() - instance.last_active
            if idle > settings.IDLE_TIMEOUT_SECONDS:
                await self.stop(
                    instance.workspace_id,
                    reason=f"stopped after {int(idle / 60)} minutes of inactivity",
                )
                return

    def _is_billable(self, instance: ComfyInstance) -> bool:
        return instance.ready

    async def _launch(self, instance: ComfyInstance):
        raise NotImplementedError

    async def _terminate(self, instance: ComfyInstance):
        raise NotImplementedError


class ModalBackend(BaseBackend):
    """A dedicated Modal sandbox per workspace (see comfy_modal.py)."""

    def __init__(self):
        super().__init__()
        self._sandboxes = {}

    async def _launch(self, instance: ComfyInstance):
        import comfy_modal

        sandbox = await asyncio.to_thread(
            comfy_modal.launch_sandbox,
            instance.workspace_id,
            gpu=settings.MODAL_GPU,
        )
        self._sandboxes[instance.workspace_id] = sandbox
        instance.instance_id = sandbox.object_id
        instance.url = await asyncio.to_thread(comfy_modal.sandbox_url, sandbox)

    async def _terminate(self, instance: ComfyInstance):
        sandbox = self._sandboxes.pop(instance.workspace_id, None)
        if sandbox:
            try:
                await asyncio.to_thread(sandbox.terminate)
            except Exception:
                logger.exception("failed to terminate modal sandbox")


class LocalBackend(BaseBackend):
    """
    Runs the same ComfyUI-per-workspace setup as ModalBackend, but as local
    subprocesses instead of Modal sandboxes (COMFY_BACKEND=local). Uses the
    local GPU when one is visible, else falls back to CPU. Needs comfy-cli
    with ComfyUI installed (`pip install comfy-cli && comfy install`).

    Billing is off by default (it's the operator's own hardware); flip
    COMFY_LOCAL_BILLING=1 to meter it like the static backend.
    """

    def __init__(self):
        super().__init__()
        self._procs: dict[int, asyncio.subprocess.Process] = {}
        self._next_port = settings.COMFY_LOCAL_PORT_START

    async def _launch(self, instance: ComfyInstance):
        import shutil
        from pathlib import Path

        if not shutil.which("comfy"):
            raise RuntimeError(
                "COMFY_BACKEND=local needs comfy-cli on PATH: "
                "`pip install comfy-cli && comfy --skip-prompt install`"
            )

        port = self._next_port
        self._next_port += 1
        base_dir = (
            Path(settings.COMFY_LOCAL_DATA_DIR).expanduser()
            / f"workspace-{instance.workspace_id}"
        )
        base_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "comfy",
            "launch",
            "--",
            "--listen",
            "127.0.0.1",
            "--port",
            str(port),
            "--base-directory",
            str(base_dir),
        ]
        if not await _has_local_gpu():
            cmd.append("--cpu")

        proc = await asyncio.create_subprocess_exec(*cmd)
        self._procs[instance.workspace_id] = proc
        instance.instance_id = f"local-{instance.workspace_id}-{int(time.time())}"
        instance.url = f"http://127.0.0.1:{port}"
        logger.info(
            f"launched local comfy for workspace {instance.workspace_id} "
            f"on port {port} (pid {proc.pid}): {' '.join(cmd)}"
        )

    async def _terminate(self, instance: ComfyInstance):
        proc = self._procs.pop(instance.workspace_id, None)
        if not proc or proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    def _is_billable(self, instance: ComfyInstance) -> bool:
        return (
            settings.COMFY_LOCAL_BILLING
            and instance.ready
            and time.time() - instance.last_active < BILLING_INTERVAL * 2
        )


async def _has_local_gpu() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await proc.wait() == 0
    except FileNotFoundError:
        return False


class StaticBackend(BaseBackend):
    """
    A single fixed upstream ComfyUI shared by all workspaces (local dev, or a
    self-managed GPU box). Billed per *active* minute since the GPU isn't
    dedicated per workspace.
    """

    async def _launch(self, instance: ComfyInstance):
        instance.instance_id = f"static-{instance.workspace_id}-{int(time.time())}"
        instance.url = settings.STATIC_COMFY_URL.rstrip("/")

    async def _terminate(self, instance: ComfyInstance):
        pass  # nothing to tear down; the upstream keeps running

    def _is_billable(self, instance: ComfyInstance) -> bool:
        return (
            instance.ready
            and time.time() - instance.last_active < BILLING_INTERVAL * 2
        )


def make_backend() -> BaseBackend:
    match settings.COMFY_BACKEND:
        case "modal":
            return ModalBackend()
        case "local":
            return LocalBackend()
        case "static":
            return StaticBackend()
    raise ValueError(f"unknown COMFY_BACKEND: {settings.COMFY_BACKEND!r}")
