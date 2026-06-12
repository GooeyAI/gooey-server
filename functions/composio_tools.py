from __future__ import annotations

import typing
from textwrap import dedent
from requests import Response

import gooey_gui as gui

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import ComposioAuthRequired
from daras_ai_v2.redis_cache import redis_cache_decorator
from functions.base_llm_tool import BaseLLMTool
import requests
import json
from daras_ai_v2.exceptions import raise_for_status

if typing.TYPE_CHECKING:
    from composio.types import Tool
    from composio import Composio
    from composio.client.types import AuthConfig
    from composio_client.types.connected_account_list_response import (
        Item as ComposioConnectedAccount,
    )
    from composio_client.types.tool_proxy_response import ToolProxyResponse


COMPOSIO_TOOL_ROUTER_SESSION_ID_KEY = "__composio_tool_router_session_id__"


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

    def bind(self, user_id: str, redirect_url: str) -> ComposioLLMTool:
        self.user_id = user_id
        self.redirect_url = redirect_url
        return self

    def call(self, **kwargs) -> dict:
        import composio_client
        from composio import Composio

        composio = Composio()
        if is_composio_meta_tool(self.tool.slug):
            session = composio.use(
                get_or_create_composio_tool_router_session_id(
                    composio,
                    user_id=self.user_id,
                    redirect_url=self.redirect_url,
                )
            )
            response = session.execute(tool_slug=self.tool.slug, arguments=kwargs)
            return {
                "data": response.data or {},
                "error": response.error,
                "successful": not response.error,
            }

        requires_auth = not self.tool.no_auth
        try:
            return composio.tools.execute(
                slug=self.tool.slug,
                user_id=self.user_id,
                arguments=kwargs,
                dangerously_skip_version_check=True,
            )
        except composio_client.BadRequestError as e:
            is_auth_error = (
                requires_auth
                and e.body
                and e.body.get("error", {}).get("code") in [1803, 1810]
            )
            if not is_auth_error:
                raise

        if requires_auth:
            toolkit = self.tool.toolkit.slug
            ensure_composio_connected_account(
                composio,
                toolkit=toolkit,
                redirect_url=self.redirect_url,
                user_id=self.user_id,
            )

        return composio.tools.execute(
            slug=self.tool.slug,
            user_id=self.user_id,
            arguments=kwargs,
            dangerously_skip_version_check=True,
        )


def is_composio_meta_tool(slug: str) -> bool:
    return slug.startswith("COMPOSIO_")


def render_composio_meta_tool_scope_warning(functions: list[dict]) -> None:
    # Meta tools share one Composio tool-router session per run, keyed to the first
    # caller's scope.
    from functions.base_llm_tool import get_external_tool_slug_from_url
    from functions.models import FunctionScopes

    composio_meta_tool_scopes = set()
    for function in functions:
        composio_tool_slug = get_external_tool_slug_from_url(
            function.get("url") or ""
        ) or function.get("slug")
        if not composio_tool_slug or not is_composio_meta_tool(composio_tool_slug):
            continue
        composio_meta_tool_scopes.add(
            function.get("scope") or FunctionScopes.workspace.name
        )
    if len(composio_meta_tool_scopes) <= 1:
        return
    gui.error(
        "Set the same scope on all Composio tools.",
        icon="⚠️",
        color="#ffe8b2",
    )


def get_or_create_composio_tool_router_session_id(
    composio: Composio,
    *,
    user_id: str,
    redirect_url: str,
) -> str:
    manage_connections = {"enable": True, "callback_url": redirect_url}

    if session_id := gui.session_state.get(COMPOSIO_TOOL_ROUTER_SESSION_ID_KEY):
        return session_id
    session = composio.create(user_id=user_id, manage_connections=manage_connections)
    gui.session_state[COMPOSIO_TOOL_ROUTER_SESSION_ID_KEY] = session.session_id
    return session.session_id


def render_inbuilt_tools_selector(key: str = "inbuilt_tools_selector") -> None:
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


def render_tool_search_dialog(function_urls: set[str]) -> None:
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


def render_toolkit_tools(toolkit: dict[str, str], function_urls: set[str]) -> None:
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
def list_toolkits() -> list[dict[str, str]]:
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
def get_tools_for_toolkit(toolkit_slug: str) -> dict[str, dict[str, str]]:
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


def ensure_composio_connected_account(
    composio: Composio,
    *,
    toolkit: str,
    redirect_url: str,
    user_id: str,
) -> None:
    get_composio_connected_accounts(
        composio,
        auth_config=get_or_create_composio_auth_config(composio, toolkit),
        redirect_url=redirect_url,
        user_id=user_id,
    )


def get_composio_connected_accounts(
    composio: Composio,
    *,
    auth_config: AuthConfig,
    redirect_url: str,
    user_id: str,
) -> list[ComposioConnectedAccount]:
    connected_accounts = composio.connected_accounts.list(
        user_ids=[user_id],
        auth_config_ids=[auth_config.id],
        statuses=["ACTIVE"],
        order_by="updated_at",
        order_direction="desc",
    )
    if not connected_accounts.items:
        connection_request = composio.connected_accounts.link(
            user_id=user_id,
            auth_config_id=auth_config.id,
            callback_url=redirect_url,
        )
        raise ComposioAuthRequired(connection_request.redirect_url)
    return connected_accounts.items


def get_or_create_composio_auth_config(composio: Composio, toolkit: str) -> AuthConfig:
    auth_configs = composio.auth_configs.list(toolkit_slug=toolkit)
    if auth_configs.items:
        return auth_configs.items[0]
    else:
        auth_config = composio.auth_configs.create(
            toolkit=toolkit,
            options={
                "type": "use_composio_managed_auth",
                "name": f"{toolkit}-gooey",
            },
        )
    return auth_config


def composio_proxy(
    *,
    endpoint: str,
    method: str,
    connected_account_id: str,
    params: dict | None = None,
) -> ToolProxyResponse:
    from composio import Composio

    if params:
        parameters = [
            dict(type="query", name=name, value=value) for name, value in params.items()
        ]
    else:
        parameters = None
    resp = Composio().tools.proxy(
        endpoint=endpoint,
        method=method,
        connected_account_id=connected_account_id,
        parameters=parameters,
    )
    if resp.status != 200:
        http_resp = _proxy_resp_to_mock_http_resp(endpoint, resp)
        raise_for_status(http_resp)
    return resp


def _proxy_resp_to_mock_http_resp(endpoint: str, resp: ToolProxyResponse) -> Response:
    http_resp = requests.Response()
    http_resp.url = endpoint
    http_resp.status_code = int(resp.status)
    if resp.headers:
        http_resp.headers.update(resp.headers)
    http_resp.reason = requests.status_codes._codes.get(
        http_resp.status_code, ["Unknown"]
    )[0]
    http_resp._content = json.dumps(resp.data).encode()
    return http_resp
