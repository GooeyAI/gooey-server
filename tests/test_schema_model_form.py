from unittest.mock import patch

import pytest

from daras_ai_v2 import schema_model_form


def test_image_size_enum_renders_selectbox():
    options = [
        "square_hd",
        "square",
        "portrait_4_3",
        "portrait_16_9",
        "landscape_4_3",
        "landscape_16_9",
    ]
    field = {
        "anyOf": [
            {"$ref": "#/components/schemas/ImageSize"},
            {"type": "string", "enum": options},
        ],
        "default": "square_hd",
    }

    with (
        patch.object(
            schema_model_form.gui, "selectbox", return_value="square_hd"
        ) as selectbox,
        patch.object(schema_model_form.gui, "file_uploader") as file_uploader,
    ):
        value = schema_model_form.render_field(
            field=field,
            name="image_size",
            label="Image Size",
            value="square_hd",
        )

    assert value == "square_hd"
    selectbox.assert_called_once_with(
        label="Image Size",
        value="square_hd",
        help=None,
        options=options,
    )
    file_uploader.assert_not_called()


@pytest.mark.parametrize(
    "name,field,value,accept_multiple_files",
    [
        ("image_url", {"type": "string"}, "https://example.com/image.png", False),
        (
            "image_urls",
            {"type": "array", "items": {"type": "string"}},
            ["https://example.com/image.png"],
            True,
        ),
    ],
)
def test_image_url_fields_render_file_uploader(
    name, field, value, accept_multiple_files
):
    with patch.object(
        schema_model_form.gui, "file_uploader", return_value=value
    ) as file_uploader:
        rendered_value = schema_model_form.render_field(
            field=field,
            name=name,
            label="Input Image",
            value=value,
        )

    assert rendered_value == value
    expected_kwargs = {
        "label": "Input Image",
        "value": value,
        "help": None,
    }
    if accept_multiple_files:
        expected_kwargs["accept_multiple_files"] = True
    file_uploader.assert_called_once_with(**expected_kwargs)
