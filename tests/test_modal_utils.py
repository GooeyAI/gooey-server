import sys

import modal

from daras_ai_v2 import modal_utils, settings

# a stand-in for a modal_functions/* module: modal requires @app.function /
# @app.cls at module scope, so this test module itself plays the app module
app = modal.App("fake-app")


@app.function()
def run_tts(language, text):
    return f"{language}:{text}"


@app.cls()
class FakeAsr:
    @modal.enter()
    def load(self):
        self.model = "loaded-model"

    @modal.method()
    def run(self, audio_url):
        return {"model": self.model, "audio": audio_url}


fake_app_module = sys.modules[__name__]


def test_modal_run_locally(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_RUN_LOCALLY", True)

    assert (
        modal_utils.get_modal_fn(fake_app_module, "run_tts").remote(
            language="eng", text="hi"
        )
        == "eng:hi"
    )

    # @modal.enter lifecycle hooks must run for local calls
    result = modal_utils.get_modal_cls(fake_app_module, "FakeAsr")().run.remote(
        audio_url="http://x/a.wav"
    )
    assert result == {"model": "loaded-model", "audio": "http://x/a.wav"}

    monkeypatch.setattr(settings, "MODAL_LOCAL_WEB_URL", "http://localhost:1234")
    assert modal_utils.get_modal_web_url(fake_app_module, "serve") == (
        "http://localhost:1234"
    )


def test_modal_run_on_cloud(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_RUN_LOCALLY", False)

    # lookups are lazy, so constructing them needs no modal credentials
    assert isinstance(
        modal_utils.get_modal_fn(fake_app_module, "run_tts"), modal.Function
    )
    assert isinstance(modal_utils.get_modal_cls(fake_app_module, "FakeAsr"), modal.Cls)
