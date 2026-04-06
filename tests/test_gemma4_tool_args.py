import json

from functions.recipe_functions import BaseLLMTool


class _EchoTool(BaseLLMTool):
    def call(self, **kwargs):
        return kwargs


def _tool() -> _EchoTool:
    return _EchoTool(name="test", label="test", description="test", properties={})


def test_clean_gemma4_tool_call_args_single_tool_call_args():
    tool = _tool()
    arguments = r'{"location":"<|\"|London<|\"|>"}'

    result = json.loads(tool.call_json(arguments))
    assert result == {"location": "London"}


def test_clean_gemma4_tool_call_args_multiple_arguments():
    tool = _tool()
    arguments = r'{"location":"<|\"|San Francisco<|\"|>","unit":"<|\"|celsius<|\"|>"}'

    result = json.loads(tool.call_json(arguments))
    assert result == {"location": "San Francisco", "unit": "celsius"}


def test_clean_gemma4_tool_call_args_nested_arguments():
    tool = _tool()
    arguments = r'{"nested":{"inner":"<|\"|value<|\"|>"},"list":["<|\"|a<|\"|>","<|\"|b<|\"|>"]}'

    result = json.loads(tool.call_json(arguments))
    assert result == {"nested": {"inner": "value"}, "list": ["a", "b"]}


def test_clean_gemma4_tool_call_args_numbers_and_boolean():
    tool = _tool()
    arguments = r'{"is_active":true,"count":42,"score":3.14}'

    result = json.loads(tool.call_json(arguments))
    assert result == {"is_active": True, "count": 42, "score": 3.14}


def test_clean_gemma4_tool_call_args_no_arguments():
    tool = _tool()
    arguments = "{}"

    result = json.loads(tool.call_json(arguments))
    assert result == {}


def test_clean_gemma4_tool_call_args_incomplete_json_returns_error():
    tool = _tool()
    arguments = r'{"location":"<|\"|London'

    result = json.loads(tool.call_json(arguments))
    assert "error" in result


def test_clean_gemma4_tool_call_args_text_unchanged():
    tool = _tool()
    assert tool._clean_gemma4_tool_call_args("normal string") == "normal string"


def test_clean_gemma4_tool_call_args_other_types_unchanged():
    tool = _tool()

    assert tool._clean_gemma4_tool_call_args(42) == 42
    assert tool._clean_gemma4_tool_call_args(3.14) == 3.14
    assert tool._clean_gemma4_tool_call_args(True) is True
    assert tool._clean_gemma4_tool_call_args(False) is False
    assert tool._clean_gemma4_tool_call_args(None) is None


def test_clean_gemma4_tool_call_args_array_with_mixed_types():
    tool = _tool()
    data = ['<|"|a<|"|>', '<|"|b<|"|>', 42, True]

    cleaned = tool._clean_gemma4_tool_call_args(data)
    assert cleaned == ["a", "b", 42, True]


def test_clean_gemma4_tool_call_args_empty_structures():
    tool = _tool()

    assert tool._clean_gemma4_tool_call_args({}) == {}
    assert tool._clean_gemma4_tool_call_args([]) == []
    assert tool._clean_gemma4_tool_call_args("") == ""
