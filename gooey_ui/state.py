import typing
from contextlib import contextmanager

from pydantic import BaseModel

_render_root: "RenderTreeNode" = None
_query_params: dict[str, str] = {}
session_state: dict[str, typing.Any] = {}


def get_query_params():
    return _query_params


def set_query_params(params: dict[str, str]):
    global _query_params
    _query_params = params


Style = dict[str, str | None]


class RenderTreeNode(BaseModel):
    name: str
    props: dict[str, typing.Any] = {}
    children: list["RenderTreeNode"] = []
    style: Style = {}

    def mount_as_root(self):
        global _render_root
        _render_root = self

    def mount(self) -> "RenderTreeNode":
        _render_root.children.append(self)
        return self


@contextmanager
def nesting_ctx(node: RenderTreeNode):
    global _render_root
    old = _render_root
    _render_root = node
    try:
        yield
    finally:
        _render_root = old


@contextmanager
def main(*, query_params: dict[str, str] = None):
    root = RenderTreeNode(name="root")
    with nesting_ctx(root):
        set_query_params(query_params or {})
        session_state.clear()
        yield root


class UploadedFile:
    pass
