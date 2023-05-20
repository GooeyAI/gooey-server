import threading
import typing

from pydantic import BaseModel

_render_root: "RenderTreeNode" = None
_query_params: dict[str, str] = {}
session_state: dict[str, typing.Any] = {}


def get_query_params():
    return _query_params


def set_query_params(params: dict[str, str]):
    _query_params.clear()
    _query_params.update(params)


def set_session_state(state: dict[str, typing.Any]):
    session_state.clear()
    session_state.update(state)


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


class NestingCtx:
    def __init__(self, node: RenderTreeNode):
        self.node = node
        self.parent = None

    def __enter__(self):
        global _render_root
        self.parent = _render_root
        _render_root = self.node

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _render_root
        _render_root = self.parent

    def empty(self):
        """Empty the children of the node"""
        self.node.children = []
        return self


def runner(
    fn: typing.Callable, state: dict = None, query_params: dict[str, str] = None
) -> dict:
    try:
        set_query_params(query_params or {})
        set_session_state(state or {})
        while True:
            try:
                root = RenderTreeNode(name="root")
                try:
                    with NestingCtx(root):
                        fn()
                except StopException:
                    pass
                # print(root.children)
                return dict(
                    state=session_state.copy(),
                    query_params=query_params.copy(),
                    children=root.children,
                )
            except RerunException:
                continue
    finally:
        set_query_params({})
        set_session_state({})


def experimental_rerun():
    raise RerunException()


def stop():
    raise StopException()


class StopException(Exception):
    pass


class RerunException(Exception):
    pass


class UploadedFile:
    pass
