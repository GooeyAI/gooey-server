import types

import modal

from daras_ai_v2 import modal_utils, settings


def _fake_app_module():
    fake = types.ModuleType("fake_modal_app")
    fake.app = modal.App("fake-app")

    @fake.app.function()
    def run_tts(language, text):
        return f"{language}:{text}"

    fake.run_tts = run_tts

    @fake.app.cls()
    class FakeAsr:
        @modal.enter()
        def load(self):
            self.model = "loaded-model"

        @modal.method()
        def run(self, audio_url):
            return {"model": self.model, "audio": audio_url}

    fake.FakeAsr = FakeAsr
    return fake


def test_modal_run_locally(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_RUN_LOCALLY", True)
    fake = _fake_app_module()

    assert (
        modal_utils.get_modal_fn(fake, "run_tts").remote(language="eng", text="hi")
        == "eng:hi"
    )

    # @modal.enter lifecycle hooks must run for local calls
    result = modal_utils.get_modal_cls(fake, "FakeAsr")().run.remote(
        audio_url="http://x/a.wav"
    )
    assert result == {"model": "loaded-model", "audio": "http://x/a.wav"}

    monkeypatch.setattr(settings, "MODAL_LOCAL_WEB_URL", "http://localhost:1234")
    assert modal_utils.get_modal_web_url(fake, "serve") == "http://localhost:1234"


def test_modal_run_on_cloud(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_RUN_LOCALLY", False)
    fake = _fake_app_module()

    # lookups are lazy, so constructing them needs no modal credentials
    assert isinstance(modal_utils.get_modal_fn(fake, "run_tts"), modal.Function)
    assert isinstance(modal_utils.get_modal_cls(fake, "FakeAsr"), modal.Cls)
