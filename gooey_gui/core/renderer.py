import inspect
import typing
from functools import partial, wraps

from fastapi import Depends
from fastapi.encoders import jsonable_encoder
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from .exceptions import RedirectException, RerunException, StopException
from .pubsub import (
    get_subscriptions,
    realtime_clear_subs,
)
from .state import get_session_state, set_session_state, set_query_params, threadlocal

Style = dict[str, str | None]
ReactHTMLProps = dict[str, typing.Any]


def current_root_ctx() -> "NestingCtx":
    return threadlocal.root_ctx


def add_styles(className: str, css: str):
    threadlocal.styles[className] = css


class RenderTreeNode:
    def __init__(
        self,
        name: str,
        props: ReactHTMLProps | None = None,
        children: list["RenderTreeNode"] | None = None,
    ):
        self.name = name
        self.props = props or {}
        self.children = children or []

    def mount(self) -> "RenderTreeNode":
        threadlocal.render_root.children.append(self)
        return self

    def to_dict(self) -> dict:
        return dict(
            name=self.name,
            props=self.props,
            children=[child.to_dict() for child in self.children],
        )


class NestingCtx:
    def __init__(self, node: RenderTreeNode | None = None):
        self.node = node or threadlocal.render_root
        self.parent = None

    def __enter__(self):
        try:
            self.parent = threadlocal.render_root
        except AttributeError:
            pass
        threadlocal.render_root = self.node

    def __exit__(self, exc_type, exc_val, exc_tb):
        threadlocal.render_root = self.parent

    def empty(self):
        """Empty the children of the node"""
        self.node.children = []
        return self


async def request_json(request: Request) -> dict | None:
    if request.headers.get("content-type") == "application/json":
        return await request.json()


def route(app, *paths, **kwargs):
    def decorator(fn):
        @wraps(fn)
        def wrapper(request: Request, json_data: dict | None, **kwargs):
            if "request" in fn_sig.parameters:
                kwargs["request"] = request
            if "json_data" in fn_sig.parameters:
                kwargs["json_data"] = json_data
            return renderer(
                partial(fn, **kwargs),
                query_params=dict(request.query_params),
                state=json_data and json_data.get("state"),
            )

        fn_sig = inspect.signature(fn)
        mod_params = dict(fn_sig.parameters) | dict(
            request=inspect.Parameter(
                "request",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            ),
            json_data=inspect.Parameter(
                "json_data",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Depends(request_json),
                annotation=typing.Optional[dict],
            ),
        )
        mod_sig = fn_sig.replace(parameters=list(mod_params.values()))
        wrapper.__signature__ = mod_sig

        for path in reversed(paths):
            wrapper = app.get(path)(wrapper)
            wrapper = app.post(path)(wrapper)

        return wrapper

    return decorator


def renderer(
    render: typing.Callable,
    state: dict[str, typing.Any] = None,
    query_params: dict[str, str] = None,
) -> dict | Response:
    set_session_state(state or {})
    set_query_params(query_params or {})
    realtime_clear_subs()
    threadlocal.use_state_count = 0
    threadlocal.styles = {}
    while True:
        try:
            root = RenderTreeNode(name="root")
            threadlocal.root_ctx = NestingCtx(root)
            with threadlocal.root_ctx:
                styles_node = RenderTreeNode(
                    name="tag",
                    props=dict(__reactjsxelement="style"),
                ).mount()
                try:
                    ret = render()
                except StopException:
                    ret = None
                except RedirectException as e:
                    return RedirectResponse(e.url, status_code=e.status_code)
                if threadlocal.styles:
                    styles_node.props["dangerouslySetInnerHTML"] = {
                        "__html": "\n".join(threadlocal.styles.values())
                    }
            if isinstance(ret, Response):
                return ret
            return JSONResponse(
                jsonable_encoder(
                    dict(
                        children=root.to_dict()["children"],
                        state=get_session_state(),
                        channels=get_subscriptions(),
                        **(ret or {}),
                    )
                ),
                headers={"X-GOOEY-GUI-ROUTE": "1"},
            )
        except RerunException:
            continue
