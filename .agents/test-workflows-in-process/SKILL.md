---
name: test-workflows-in-process
description: Use when reproducing or inspecting Gooey workflow behavior locally without the browser, especially for capturing VideoBots prompts, tool-call traces, workflow-tool arguments, or comparing prompt/schema changes against a published run.
---

# Test Workflows In Process

## Overview
Run Gooey workflows directly in Python against real published-run state when you need prompt and tool-call evidence faster than a browser or API round-trip.

Core principle: reproduce the real workflow state first, then stub downstream workflow execution only if you need prompt/tool traces without waiting for the called workflow to finish.

## When To Use
- You need the exact `final_prompt` sent to the LLM.
- You need raw `tool_calls` emitted by `VideoBotsPage`.
- You want to compare prompt/schema changes against the same published run.
- A downstream workflow is slow or flaky, but you still need the tool arguments.
- You want to inspect a published copilot URL like `/copilot/<slug>-<example_id>/`.

Do not use this when the behavior depends on browser-only UI interactions. Use browser testing for that.

## Setup

```python
__import__("gooeysite.wsgi")
```

## Workflow Pattern
1. Parse the published run ID from the URL.
2. Build the page class directly, usually `VideoBotsPage(...)`.
3. Load real state with `page.current_sr_to_session_state()`.
4. Override only the fields needed for the experiment:
   - `messages`
   - `input_prompt`
   - `output_text`
   - `raw_output_text`
   - `final_prompt`
   - `output_audio`
5. Call `gui.set_session_state(state)`.
6. Patch `get_current_workspace()` to return the published-run workspace.
7. Run `page.run(gui.session_state)`.
8. Read `gui.session_state["final_prompt"]`, `output_text`, and any assistant `tool_calls`.

## Base Script Template

```python
__import__("gooeysite.wsgi")

import json

import gooey_gui as gui
from starlette.datastructures import URL
from unittest.mock import patch

from bots.models import get_default_published_run_workspace
from recipes.VideoBots import VideoBotsPage
from workspaces.models import Workspace

example_id = "v1xm6uhp"
request_url = URL("http://localhost:3000/copilot/base-copilot-w-search-rag-code-execution-v1xm6uhp/")
workspace = Workspace.objects.get(id=get_default_published_run_workspace())
user = workspace.created_by

page = VideoBotsPage(
    user=user,
    request_session={},
    request_url=request_url,
    query_params={"example_id": example_id, "uid": user.uid},
)

state = page.current_sr_to_session_state()
state.update(
    {
        "messages": [],
        "input_prompt": "Your test input here",
        "output_text": [],
        "raw_output_text": [],
        "final_prompt": [],
        "output_audio": [],
    }
)
gui.set_session_state(state)

progress = []
with patch("daras_ai_v2.base.get_current_workspace", return_value=workspace):
    for step in page.run(gui.session_state):
        if step:
            progress.append(step)

final_state = dict(gui.session_state)
print(json.dumps(
    {
        "progress": progress,
        "final_prompt": final_state.get("final_prompt"),
        "output_text": final_state.get("output_text"),
        "error_msg": final_state.get("error_msg"),
    },
    indent=2,
    default=str,
))
```

## Capturing Tool Traces
To capture assistant-emitted tool calls from `VideoBotsPage`:

```python
assistant_entries = [
    entry for entry in final_state.get("final_prompt", [])
    if entry.get("role") == "assistant"
]

trace = []
for entry in assistant_entries:
    for call in entry.get("tool_calls") or []:
        trace.append(
            {
                "id": call.get("id"),
                "name": call.get("function", {}).get("name"),
                "arguments": call.get("function", {}).get("arguments"),
                "label": call.get("label"),
                "content": entry.get("content"),
            }
        )
```

## Stubbing Workflow Tools
If a workflow tool is slow or triggers another full run, stub `WorkflowLLMTool.call` and capture its kwargs instead of executing it:

```python
from functions.base_llm_tool import WorkflowLLMTool

captured_calls = []


def fake_call(self, **kwargs):
    captured_calls.append(
        {
            "name": self.name,
            "label": self.label,
            "description": self.spec_function["description"],
            "kwargs": kwargs,
            "spec_parameters": self.spec_parameters,
        }
    )
    return {"stubbed": True, "tool_name": self.name, "kwargs": kwargs}


with (
    patch("daras_ai_v2.base.get_current_workspace", return_value=workspace),
    patch.object(WorkflowLLMTool, "call", fake_call),
):
    for step in page.run(gui.session_state):
        ...
```

Use this when you care about:
- the exact tool arguments
- the tool description/schema shown to the model
- the final prompt and assistant text

## Editing The Copilot Prompt For Experiments
To test prompt sensitivity without modifying saved workflow data, edit `state["bot_script"]` in memory before `gui.set_session_state(state)`.

Good use cases:
- remove one tool instruction block
- rewrite one tool hint
- compare before/after prompt wording

## Reporting Format
When you finish, report:
- the workflow URL or `example_id`
- the exact user input sequence used
- the relevant system prompt excerpt
- the raw `tool_call_trace`
- the captured workflow-tool kwargs if stubbing
- whether the downstream workflow was real or stubbed
- the resulting `output_text`

## Common Pitfalls
- Anonymous users fail when tool binding needs a workspace. Use the published-run owner workspace and patch `get_current_workspace()`.
- Real workflow execution can hang or run long. Stub `WorkflowLLMTool.call` when you only need tool traces.
- Clear `messages`, `final_prompt`, and output fields between experiments or you will mix traces.
- If comparing prompt variants, keep the same `example_id` and same user-turn sequence.
