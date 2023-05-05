import typing
from contextlib import contextmanager

from pydantic import BaseModel

render_root: "RenderTreeNode" = None

Style = dict[str, str | None]


class RenderTreeNode(BaseModel):
    name: str
    props: dict[str, typing.Any] = {}
    children: list["RenderTreeNode"] = []
    style: Style = {}

    def mount(self) -> "RenderTreeNode":
        render_root.children.append(self)
        return self


@contextmanager
def nesting_ctx(node: RenderTreeNode):
    global render_root
    old = render_root
    render_root = node
    try:
        yield
    finally:
        render_root = old


class UploadedFile:
    pass
