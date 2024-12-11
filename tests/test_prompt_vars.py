import pytest

from daras_ai_v2.variables_widget import render_prompt_vars


@pytest.mark.parametrize(
    "prompt,state,variables,expected",
    [
        ("{{ a }}", {"a": "b"}, {"a": "c"}, "c"),
        ("{{ a }}", {"a": "b"}, {}, "b"),
        ("{{ a }}", {}, {"a": "c"}, "c"),
        ("{{ a }}", {}, {}, ""),
        ("{{ a }}", {"a": "b"}, {"a": ""}, ""),
        ("{{ a }}", {"a": ""}, {"a": "c"}, "c"),
        ("{{ a }}", {"a": None}, {}, ""),
        ("{{ a }}", {}, {"a": None}, ""),
        ("{{ a }}", {"a": None}, {"a": "c"}, "c"),
        ("{{ a }}", {"a": "b"}, {"a": None}, ""),
        ("{{ a }}", {"a": "b"}, {"a": ""}, ""),
        ("{{ a }}", {"a": ""}, {"a": "c"}, "c"),
        ("{{ a }}", {"a": ""}, {"a": ""}, ""),
        ("{{ a }}", {"a": None}, {"a": None}, ""),
        ("{{ a }}", {"a": 5}, {}, "5"),
    ],
)
def test_prompt_vars(prompt, state, variables, expected):
    state["variables"] = variables
    assert render_prompt_vars(prompt, state) == expected
