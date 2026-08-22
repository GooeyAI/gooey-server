"""
Helpers for calling Modal workloads (modal_functions/*), honoring the global
settings.MODAL_RUN_LOCALLY flag.

With the flag off (default), lookups go to the deployed Modal apps and run on
Modal's cloud. With the flag on, the same calls execute in-process on this
machine via modal's `.local()` — using the local GPU if the model code finds
one — so local installs can run every Modal-backed feature without a Modal
account. Call sites keep the standard `.remote()` spelling; the proxies below
reroute it.

Not covered by the flag: `modal.Sandbox` usage (recipes/Functions.py code
execution, the ComfyUI cloud sandboxes) — those exist to isolate untrusted
code, so silently running them on the host would be unsafe. The ComfyUI
gateway has its own COMFY_BACKEND=local mode (comfy/README.md), which this
flag switches on by default.

### Usage

```python
from daras_ai_v2.modal_utils import get_modal_fn, get_modal_cls
from modal_functions import mms_tts, sravaani_asr

get_modal_fn(mms_tts, "run_mms_tts").remote(language="eng", text=...)
get_modal_cls(sravaani_asr, "SraVaani")().run.remote(audio_url=...)
```
"""

import typing

import modal

from daras_ai_v2 import settings


def get_modal_fn(app_module: typing.Any, name: str):
    """A modal Function with `.remote()`, local or cloud per MODAL_RUN_LOCALLY."""
    if settings.MODAL_RUN_LOCALLY:
        return _LocalCallableProxy(getattr(app_module, name))
    return modal.Function.from_name(app_module.app.name, name)


def get_modal_cls(app_module: typing.Any, name: str):
    """A modal Cls whose instance methods support `.remote()`, local or cloud."""
    if settings.MODAL_RUN_LOCALLY:
        return _LocalClsProxy(getattr(app_module, name))
    return modal.Cls.from_name(app_module.app.name, name)


def get_modal_web_url(app_module: typing.Any, name: str) -> str:
    """
    URL of a modal web endpoint. Web servers (e.g. the agri_llm vLLM server)
    can't be run in-process, so in local mode this points at
    settings.MODAL_LOCAL_WEB_URL — start the equivalent server yourself, e.g.:

        vllm serve AI71ai/agri-fanar-27b-chat --port 8000
    """
    if settings.MODAL_RUN_LOCALLY:
        return settings.MODAL_LOCAL_WEB_URL
    return modal.Function.from_name(app_module.app.name, name).get_web_url()


class _LocalCallableProxy:
    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return self._fn.local(*args, **kwargs)


class _LocalObjProxy:
    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        return _LocalCallableProxy(getattr(self._obj, name))


class _LocalClsProxy:
    def __init__(self, cls):
        self._cls = cls

    def __call__(self, *args, **kwargs):
        return _LocalObjProxy(self._cls(*args, **kwargs))
