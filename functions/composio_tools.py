from __future__ import annotations

import typing
from textwrap import dedent

import gooey_gui as gui

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.redis_cache import redis_cache_decorator
from functions.recipe_functions import BaseLLMTool

if typing.TYPE_CHECKING:
    from composio.types import Tool


class ComposioLLMTool(BaseLLMTool):
    def __init__(self, tool: Tool, scope: str | None):
        self.tool = tool
        self.scope = scope
        super().__init__(
            name=tool.slug,
            label=tool.name,
            description=tool.description,
            properties=tool.input_parameters["properties"],
            required=tool.input_parameters.get("required"),
        )

    def bind(self, user_id: str, redirect_url: str):
        self.user_id = user_id
        self.redirect_url = redirect_url
        return self

    def call(self, **kwargs) -> dict:
        import composio_client
        from composio import Composio

        requires_auth = not self.tool.no_auth

        composio = Composio()
        try:
            return composio.tools.execute(
                slug=self.tool.slug,
                user_id=self.user_id,
                arguments=kwargs,
                dangerously_skip_version_check=True,
            )
        except composio_client.BadRequestError as e:
            is_auth_error = (
                requires_auth and e.body and e.body.get("error", {}).get("code") == 1803
            )
            if not is_auth_error:
                raise

        if requires_auth:
            toolkit = self.tool.toolkit.slug
            auth_configs = composio.auth_configs.list(toolkit_slug=toolkit)
            if auth_configs.items:
                auth_config = auth_configs.items[0]
            else:
                auth_config = composio.auth_configs.create(
                    toolkit=toolkit,
                    options={
                        "type": "use_composio_managed_auth",
                        "name": f"{toolkit}-gooey",
                    },
                )

            connected_accounts = composio.connected_accounts.list(
                user_ids=[self.user_id],
                auth_config_ids=[auth_config.id],
                statuses=["ACTIVE"],
            )
            if not connected_accounts.items:
                connection_request = composio.connected_accounts.link(
                    user_id=self.user_id,
                    auth_config_id=auth_config.id,
                    callback_url=self.redirect_url,
                )
                raise UserError(
                    f"Please authenticate {connection_request.redirect_url}"
                )

        return composio.tools.execute(
            slug=self.tool.slug, user_id=self.user_id, arguments=kwargs
        )


def render_inbuilt_tools_selector(key="inbuilt_tools_selector"):
    dialog_ref = gui.use_alert_dialog(key)

    if gui.button(
        label='<i class="fa-solid fa-octagon-plus"></i> Add Integrations',
        key="select_tools",
        type="tertiary",
        className="p-1 mb-2",
    ):
        dialog_ref.set_open(True)

    if not dialog_ref.is_open:
        gui.session_state.pop("__tools_cache__", None)
        for k in list(gui.session_state.keys()):
            if k.startswith("inbuilt_tool:"):
                gui.session_state.pop(k, None)
        return

    function_urls = {
        function.get("url", "") for function in gui.session_state.get("functions", [])
    }

    with gui.alert_dialog(
        ref=dialog_ref,
        modal_title="#### 🧰 Add Integrations",
        large=True,
    ):
        render_tool_search_dialog(function_urls)
        with gui.div(
            className="d-flex justify-content-end mt-2 container-margin-reset"
        ):
            gui.write(f"{len(function_urls)} integrations selected")


def render_tool_search_dialog(function_urls: set[str]):
    if not settings.COMPOSIO_API_KEY:
        gui.error(
            "Please set the COMPOSIO_API_KEY environment variable to use this feature."
        )
        return

    query = gui.text_input(label="", placeholder="Search integrations...")

    with (
        gui.styled("& .gui-expander-header { padding: 0.5rem; }"),
        gui.div(
            className="overflow-auto container-margin-reset",
            style={"maxHeight": "50vh"},
        ),
    ):
        toolkits = [
            dict(
                name="Gooey.AI Memory",
                slug="GOOEY_AI_MEMORY",
                logo="https://gooey.ai/favicon.ico",
                description="Securely store key user data such as their consent, location or other other info you want your AI agent to remember across sessions and conversations.",
                search_terms="gooey.ai gooeyai storage data user consent location remember conversation session",
            )
        ] + list_toolkits()

        query_words = query.lower().split()
        if query_words:
            toolkits = [
                toolkit
                for toolkit in toolkits
                if all(word in toolkit["search_terms"] for word in query_words)
            ]

        for toolkit in toolkits[:50]:
            render_toolkit_tools(toolkit, function_urls)


def render_toolkit_tools(toolkit: dict, function_urls: set[str]):
    from daras_ai_v2.fastapi_tricks import get_app_route_url
    from routers.root import tool_page

    expander_key = f"inbuilt_toolkit:{toolkit['slug']}"
    with (
        gui.expander(
            label=(
                f"<img src='{toolkit['logo']}' width='16' height='16' class='me-1 mb-1' /> "
                f"**{toolkit['name']}**<br>"
                f"<span class='text-muted small'>{toolkit['description']}</span>"
            ),
            key=expander_key,
        ),
    ):
        if not gui.session_state.get(expander_key):
            return

        toolkit_slug = toolkit["slug"]
        if toolkit_slug == "GOOEY_AI_MEMORY":
            tools = {
                "GOOEY_MEMORY_READ_VALUE": dict(
                    name="Read Value",
                    slug="GOOEY_MEMORY_READ_VALUE",
                    description="Read the value of a key from the Gooey.AI store.",
                ),
                "GOOEY_MEMORY_WRITE_VALUE": dict(
                    name="Write Value",
                    slug="GOOEY_MEMORY_WRITE_VALUE",
                    description="Write a value to the Gooey.AI store.",
                ),
                "GOOEY_MEMORY_DELETE_VALUE": dict(
                    name="Delete Value",
                    slug="GOOEY_MEMORY_DELETE_VALUE",
                    description="Delete a value from the Gooey.AI store.",
                ),
            }
        else:
            tools = get_tools_for_toolkit(toolkit_slug)
        for tool in tools.values():
            with gui.div(className="d-flex gap-2"):
                url = get_app_route_url(
                    tool_page,
                    path_params=dict(toolkit_slug=toolkit_slug, tool_slug=tool["slug"]),
                )
                functions = gui.session_state.setdefault("functions", [])
                if gui.checkbox(
                    label=tool["name"],
                    help=dedent(tool["description"]),
                    key=f"inbuilt_tool:{toolkit['slug']}/{tool['slug']}",
                    value=url in function_urls,
                ):
                    if url not in function_urls:
                        functions.append(
                            {
                                "trigger": "prompt",
                                "url": url,
                                "label": tool["name"],
                                "logo": toolkit["logo"],
                            }
                        )
                        function_urls.add(url)
                else:
                    if url in function_urls:
                        function_urls.remove(url)
                        for i in range(len(functions)):
                            if functions[i]["url"] == url:
                                functions.pop(i)
                                break


@redis_cache_decorator(ex=60 * 60 * 24)  # 1 day
def list_toolkits():
    from composio import Composio

    return [
        dict(
            name=item.name,
            slug=item.slug,
            logo=item.meta.logo,
            description=item.meta.description,
            search_terms=" ".join(
                [
                    item.name,
                    item.meta.description,
                    *[category.name for category in item.meta.categories],
                ]
            ).lower(),
        )
        for item in Composio().toolkits.list(limit=1000).items
    ]


@gui.cache_in_session_state(key="__tools_cache__")
def get_tools_for_toolkit(toolkit_slug: str) -> dict[str, dict]:
    from composio import Composio

    return {
        item.slug: dict(
            name=item.name,
            slug=item.slug,
            description=item.description,
        )
        for item in Composio().tools.get_raw_composio_tools(
            toolkits=[toolkit_slug], limit=9999
        )
    }
