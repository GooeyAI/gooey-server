from unittest.mock import Mock, patch

import pytest

from daras_ai_v2.asr import asr_model_ids, AsrModels, run_asr
from daras_ai_v2.exceptions import UserError


AUDIO_URL = "https://example.com/audio.wav"
TRANSCRIPT = "Test transcription"
OPENAI_ASR_MODELS = (
    AsrModels.gpt_transcribe,
    AsrModels.gpt_4_o_audio,
    AsrModels.gpt_4_o_mini_audio,
)


@pytest.mark.parametrize("selected_model", OPENAI_ASR_MODELS)
@pytest.mark.parametrize(
    ("output_format", "expected"),
    [("text", TRANSCRIPT), ("json", {"text": TRANSCRIPT})],
)
def test_openai_asr_output_format(selected_model, output_format, expected):
    audio_response = Mock(
        status_code=200,
        reason="OK",
        url=AUDIO_URL,
        content=b"audio",
    )
    client = Mock()
    client.audio.transcriptions.create.return_value = Mock(text=TRANSCRIPT)

    with (
        patch(
            "daras_ai_v2.asr.audio_url_to_wav_url",
            return_value=(AUDIO_URL, 1),
        ),
        patch("daras_ai_v2.asr.requests.get", return_value=audio_response),
        patch(
            "daras_ai_v2.language_model.get_openai_client",
            return_value=client,
        ),
    ):
        result = run_asr(
            audio_url=AUDIO_URL,
            selected_model=selected_model.name,
            output_format=output_format,
        )

    assert result == expected
    client.audio.transcriptions.create.assert_called_once_with(
        model=asr_model_ids[selected_model],
        file=(AUDIO_URL, b"audio"),
        prompt=None,
        response_format="json",
    )


@pytest.mark.parametrize("selected_model", OPENAI_ASR_MODELS)
@pytest.mark.parametrize("output_format", ["srt", "vtt"])
def test_openai_asr_rejects_timestamp_formats(selected_model, output_format):
    with (
        patch(
            "daras_ai_v2.asr.audio_url_to_wav_url",
            return_value=(AUDIO_URL, 1),
        ),
        patch("daras_ai_v2.asr.requests.get") as requests_get,
        pytest.raises(UserError, match=f"can't generate {output_format.upper()}"),
    ):
        run_asr(
            audio_url=AUDIO_URL,
            selected_model=selected_model.name,
            output_format=output_format,
        )

    requests_get.assert_not_called()
