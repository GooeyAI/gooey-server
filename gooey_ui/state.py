import threading
import typing

from pydantic import BaseModel

from gooey_ui.pubsub import (
    get_subscriptions,
    clear_subscriptions,
)

threadlocal = threading.local()


def __getattr__(name):
    if name == "session_state":
        return get_session_state()
    else:
        raise AttributeError(name)


def get_query_params() -> dict[str, str]:
    try:
        return threadlocal.query_params
    except AttributeError:
        threadlocal.query_params = {}
        return threadlocal.query_params


def set_query_params(params: dict[str, str]):
    threadlocal.query_params = params


def get_session_state() -> dict[str, typing.Any]:
    try:
        return threadlocal.session_state
    except AttributeError:
        threadlocal.session_state = {}
        return threadlocal.session_state


def set_session_state(state: dict[str, typing.Any]):
    threadlocal.session_state = state


Style = dict[str, str | None]


class RenderTreeNode(BaseModel):
    name: str
    props: dict[str, typing.Any] = {}
    children: list["RenderTreeNode"] = []
    style: Style = {}

    def mount(self) -> "RenderTreeNode":
        threadlocal._render_root.children.append(self)
        return self


class NestingCtx:
    def __init__(self, node: RenderTreeNode = None):
        self.node = node or threadlocal._render_root
        self.parent = None

    def __enter__(self):
        try:
            self.parent = threadlocal._render_root
        except AttributeError:
            pass
        threadlocal._render_root = self.node

    def __exit__(self, exc_type, exc_val, exc_tb):
        threadlocal._render_root = self.parent

    def empty(self):
        """Empty the children of the node"""
        self.node.children = []
        return self


def runner(
    fn: typing.Callable,
    state: dict[str, typing.Any] = None,
    query_params: dict[str, str] = None,
    # channels: list[str] = None,
    # session_id: str = None,
) -> dict:
    set_session_state(state or {})
    set_query_params(query_params or {})
    clear_subscriptions()
    # subscibe(channels or {})
    # pubsub.threadlocal.session_id = session_id
    while True:
        try:
            root = RenderTreeNode(name="root")
            try:
                with NestingCtx(root):
                    fn()
            except StopException:
                pass
            return dict(
                children=root.children,
                state=get_session_state(),
                # query_params=get_query_params(),
                channels=get_subscriptions(),
            )
        except RerunException:
            continue


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
