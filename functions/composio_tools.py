from __future__ import annotations

import typing
from textwrap import dedent

import gooey_gui as gui

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.redis_cache import redis_cache_decorator
from functions.recipe_functions import BaseLLMTool, get_external_tool_slug_from_url
from workspaces.models import Workspace

if typing.TYPE_CHECKING:
    from composio.types import Tool, Toolkit


def get_external_tools_from_state(state: dict) -> typing.Iterable[ComposioLLMTool]:
    from composio import Composio

    functions = state.get("functions")
    if not functions:
        return
    tool_slugs = {
        tool_slug
        for function in functions
        if (tool_slug := get_external_tool_slug_from_url(function["url"]))
    }
    for tool in Composio().tools.get_raw_composio_tools(tools=tool_slugs, limit=50):
        yield ComposioLLMTool(tool)


class ComposioLLMTool(BaseLLMTool):
    def __init__(self, tool: Tool):
        self.tool = tool
        super().__init__(
            name=tool.slug,
            label=tool.name,
            description=tool.description,
            properties=tool.input_parameters["properties"],
            required=tool.input_parameters.get("required"),
        )

    def bind(self, workspace: Workspace, redirect_url: str):
        self.workspace = workspace
        self.redirect_url = redirect_url
        return self

    def call(self, **kwargs) -> dict:
        from composio import Composio
        import composio_client

        user_id = f"gooey-workspace-{self.workspace.id}"
        requires_auth = not self.tool.no_auth

        composio = Composio()
        try:
            return composio.tools.execute(
                slug=self.tool.slug,
                user_id=user_id,
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
                user_ids=[user_id],
                auth_config_ids=[auth_config.id],
                statuses=["ACTIVE"],
            )
            if not connected_accounts.items:
                connection_request = composio.connected_accounts.link(
                    user_id=user_id,
                    auth_config_id=auth_config.id,
                    callback_url=self.redirect_url,
                )
                raise UserError(
                    f"Please authenticate {connection_request.redirect_url}"
                )

        return composio.tools.execute(
            slug=self.tool.slug, user_id=user_id, arguments=kwargs
        )


def render_inbuilt_tools_selector(key="inbuilt_tools_selector"):
    from daras_ai_v2.fastapi_tricks import get_app_route_url
    from routers.root import tool_page

    dialog_ref = gui.use_confirm_dialog(key)

    if gui.button(
        label='<i class="fa-solid fa-octagon-plus"></i> Add External',
        key="select_tools",
        type="tertiary",
        className="p-1 mb-2",
    ):
        dialog_ref.set_open(True)

    selected_keys = [
        k for k, v in gui.session_state.items() if v and k.startswith("inbuilt_tool:")
    ]

    if dialog_ref.pressed_confirm:
        functions = gui.session_state.setdefault("functions", [])
        existing_urls = {f["url"] for f in functions}
        for k in selected_keys:
            toolkit_slug, tool_slug = k.removeprefix("inbuilt_tool:").split("/")
            url = get_app_route_url(
                tool_page,
                path_params=dict(toolkit_slug=toolkit_slug, tool_slug=tool_slug),
            )
            if url in existing_urls:
                continue
            functions.append({"trigger": "prompt", "url": url})

    if not dialog_ref.is_open:
        gui.session_state.pop("__tools_cache__", None)
        for k in selected_keys:
            gui.session_state.pop(k, None)
        return

    confirm_label = "Add"
    if selected_keys:
        confirm_label += f" {len(selected_keys)} Tools"

    with gui.confirm_dialog(
        ref=dialog_ref,
        modal_title="#### 🧰 Add External Tools",
        large=True,
        confirm_label=confirm_label,
    ):
        render_tool_search_dialog()


def render_tool_search_dialog():
    if not settings.COMPOSIO_API_KEY:
        gui.error(
            "Please set the COMPOSIO_API_KEY environment variable to use this feature."
        )
        return

    query = gui.text_input(label="", placeholder="Search for a tool...")

    with (
        gui.styled("& .gui-expander-header { padding: 0.5rem; }"),
        gui.div(
            className="overflow-auto container-margin-reset",
            style={"maxHeight": "50vh"},
        ),
    ):
        toolkits = get_toolkits()

        query_words = query.lower().split()
        if query_words:
            toolkits = [
                toolkit
                for toolkit in toolkits
                if all(
                    word in toolkit.name.lower()
                    or word in toolkit.meta.description.lower()
                    or any(
                        word in category.name.lower()
                        for category in toolkit.meta.categories
                    )
                    for word in query_words
                )
            ]

        for toolkit in toolkits[:50]:
            render_toolkit_tools(toolkit)


def render_toolkit_tools(toolkit: Toolkit):
    expander_key = f"inbuilt_toolkit:{toolkit.slug}"
    with (
        gui.expander(
            label=(
                f"<img src='{toolkit.meta.logo}' width='16' height='16' class='me-1 mb-1' /> "
                f"**{toolkit.name}**<br>"
                f"<span class='text-muted small'>{toolkit.meta.description}</span>"
            ),
            key=expander_key,
        ),
    ):
        if not gui.session_state.get(expander_key):
            return

        tools = get_tools_for_toolkit(toolkit.slug)
        for tool in tools:
            with gui.div(className="d-flex gap-2"):
                gui.checkbox(
                    label=tool["name"],
                    help=dedent(tool["description"]),
                    key=f"inbuilt_tool:{toolkit.slug}/{tool['slug']}",
                )


@redis_cache_decorator(ex=60 * 60 * 24)  # 1 day
def get_toolkits():
    from composio import Composio

    return Composio().toolkits.list(limit=1000).items


@gui.cache_in_session_state(key="__tools_cache__")
def get_tools_for_toolkit(toolkit_slug: str) -> list[Tool]:
    from composio import Composio

    return [
        {
            "name": item.name,
            "slug": item.slug,
            "description": item.description,
        }
        for item in Composio().tools.get_raw_composio_tools(
            toolkits=[toolkit_slug], limit=9999
        )
    ]
