from functions.recipe_functions import (
    BaseLLMTool,
    generate_tool_properties,
)


class UpdateGuiStateLLMTool(BaseLLMTool):
    def __init__(self, builder_state: dict, page_slug: str):
        from daras_ai_v2.all_pages import normalize_slug, page_slug_map

        request = builder_state.get("request", builder_state)
        try:
            page_cls = page_slug_map[normalize_slug(page_slug)]
        except KeyError:
            properties = dict(generate_tool_properties(request, {}))
        else:
            properties = page_cls.get_tool_call_schema(request)

        properties["-submit-workflow"] = {
            "type": "boolean",
            "description": "Submit & Run the workflow.",
        }

        super().__init__(
            name="update_gui_state",
            label="Update Workflow",
            description="Update the current GUI state.",
            properties=properties,
        )

    def call(self, **kwargs) -> str:
        # handled by the frontend in gooey-web-widget
        return "ok"


class RunJS(BaseLLMTool):
    def __init__(self):
        super().__init__(
            name="run_js",
            label="Run JS",
            description="Run arbitrary JS code on the frontend",
            properties={
                "js_code": {
                    "type": "string",
                    "description": "The JS code to run on the frontend.",
                }
            },
        )

    def call(self, js_code: str) -> str:
        # handled by the frontend in gooey-web-widget
        return "ok"
