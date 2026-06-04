import types

from daras_ai_v2 import workflow_url_input
from gooey_gui.core.state import URL_TO_RUNS_CACHE_ATTR, threadlocal


def test_url_to_runs_uses_per_render_cache(monkeypatch):
    calls = []
    page_cls = types.SimpleNamespace(workflow=4)
    sr = types.SimpleNamespace()
    pr = types.SimpleNamespace()

    monkeypatch.setattr(
        workflow_url_input,
        "resolve_url_to_runs",
        lambda url: calls.append(url) or (page_cls, sr, pr),
    )
    threadlocal.__dict__.pop(URL_TO_RUNS_CACHE_ATTR, None)
    url = "https://gooey.ai/copilot/example/"

    assert workflow_url_input.url_to_runs(url) == (page_cls, sr, pr)
    assert workflow_url_input.url_to_runs(url) == (page_cls, sr, pr)
    assert calls == [url]
