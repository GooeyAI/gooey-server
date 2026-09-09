from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from requests.utils import CaseInsensitiveDict

from ai_models.models import AIModelSpec
from daras_ai_v2.exceptions import PaymentRequired, UserError
from recipes import ImageGenPage as image_gen
from recipes import VideoGenPage as video_gen


@pytest.mark.parametrize(
    "result,expected",
    [
        (
            {
                "images": [
                    {"url": "https://example.com/1.png"},
                    {"url": "https://example.com/2.png"},
                ]
            },
            ["https://example.com/1.png", "https://example.com/2.png"],
        ),
        (
            {"image": {"url": "https://example.com/1.png"}},
            ["https://example.com/1.png"],
        ),
    ],
)
def test_generation_returns_images(image_page, result, expected):
    page, request, response = image_page
    with patch.object(
        image_gen, "generate_on_fal", return_value=iter_result(result)
    ) as generate:
        assert list(page.run_v2(request, response)) == [
            "Running Test Image",
            "Generating",
        ]

    assert response.output_images == {"test-image": expected}
    generate.assert_called_once_with(
        "fal-ai/test-image", {"prompt": "A cat", "enable_safety_checker": False}
    )


@pytest.mark.parametrize(
    "result", [{}, {"images": []}, {"moderation_flagged": True}, []]
)
def test_invalid_or_moderated_output_is_rejected(image_page, result):
    page, request, response = image_page
    with patch.object(image_gen, "generate_on_fal", return_value=iter_result(result)):
        with pytest.raises(UserError):
            list(page.run_v2(request, response))
    assert response.output_images == {}


@pytest.mark.parametrize("failure", ["no_model", "missing_prompt", "paid_only"])
def test_invalid_request_does_not_call_provider(image_page, failure):
    page, request, response = image_page
    if failure == "no_model":
        request.selected_model = None
    elif failure == "missing_prompt":
        request.inputs = {}
    else:
        page.get_model.return_value.paid_only = True
    with patch.object(image_gen, "generate_on_fal") as generate:
        with pytest.raises(PaymentRequired if failure == "paid_only" else UserError):
            list(page.run_v2(request, response))
    generate.assert_not_called()


@pytest.mark.parametrize("selected_model", ["TEST-IMAGE", "another-model", None])
def test_preview_only_shows_selected_model(image_page, selected_model):
    page, _, _ = image_page
    page.available_models = CaseInsensitiveDict(
        {"test-image": page.get_model.return_value}
    )
    with patch.object(image_gen.gui, "image") as image:
        page.render_run_preview_output(
            {
                "selected_model": selected_model,
                "output_images": {"test-image": ["https://example.com/1.png"]},
            },
            preview=False,
        )
    assert image.call_count == (selected_model == "TEST-IMAGE")


def test_image_and_video_reuse_prompt_checks(image_page):
    page, request, response = image_page
    page.request.user.disable_safety_checker = False
    inputs = {"prompt": "A cat"}
    video_page = video_gen.VideoGenPage(user=page.request.user)
    video_request = video_page.RequestModel(
        selected_models=["test-video"], inputs=inputs, audio_inputs={"prompt": "A meow"}
    )
    with (
        patch.object(video_gen.gui, "session_state", {}),
        patch.object(video_gen, "safety_checker") as safety,
        patch.object(
            image_gen,
            "generate_on_fal",
            return_value=iter_result({"image": "https://example.com/1.png"}),
        ),
    ):
        list(page.run_v2(request, response))
        assert safety.call_count == 1
        list(video_page.run_safety_checker(video_request))
        assert [call.kwargs["text"] for call in safety.call_args_list] == [
            "A cat",
            "A cat",
            "A meow",
        ]


@pytest.fixture
def image_page():
    page = image_gen.ImageGenPage(user=SimpleNamespace(disable_safety_checker=True))
    page.current_workspace = SimpleNamespace(is_paying=False)
    page.get_model = Mock(
        return_value=AIModelSpec(
            name="test-image",
            label="Test Image",
            model_id="fal-ai/test-image",
            paid_only=False,
            schema={
                "properties": {"prompt": {"type": "string"}},
                "required": ["prompt"],
            },
        )
    )
    request = page.RequestModel(selected_model="test-image", inputs={"prompt": "A cat"})
    response = page.ResponseModel(output_images={})
    return page, request, response


def iter_result(result):
    yield "Generating"
    return result
