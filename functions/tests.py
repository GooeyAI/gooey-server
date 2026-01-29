from bots.models.saved_run import SavedRun
from functions.models import CalledFunction, FunctionTrigger
from functions.recipe_functions import _get_external_tool_calls_items


def test_external_tool_calls_skip_called_workflow_tools(transactional_db):
    saved_run = SavedRun.objects.create(
        state={
            "final_prompt": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "my_tool", "arguments": '{"foo": 1}'},
                        },
                        {
                            "id": "call_2",
                            "function": {
                                "name": "other_tool",
                                "arguments": '{"bar": 2}',
                            },
                        },
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_2",
                    "content": '{"ok": true}',
                },
            ]
        }
    )
    function_run = SavedRun.objects.create(state={})
    called_fn = CalledFunction.objects.create(
        saved_run=saved_run,
        function_run=function_run,
        trigger=FunctionTrigger.prompt.db_value,
        tool_name="my_tool",
    )

    items = list(
        _get_external_tool_calls_items(saved_run, called_functions=[called_fn])
    )
    items_by_id = {item["id"]: item for item in items}

    assert "call_1" not in items_by_id
    assert items_by_id["call_2"]["title"] == "other_tool"
    assert items_by_id["call_2"]["inputs"] == {"bar": 2}
    assert items_by_id["call_2"]["return_value"] == {"ok": True}
    assert items_by_id["call_2"]["is_running"] is False
