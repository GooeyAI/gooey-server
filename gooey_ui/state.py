import threading
import typing

from pydantic import BaseModel

_local = threading.local()


def __getattr__(name):
    if name == "session_state":
        return get_session_state()
    else:
        raise AttributeError(name)


def get_query_params():
    try:
        return _local._query_params
    except AttributeError:
        _local._query_params = {}
        return _local._query_params


def set_query_params(params: dict[str, str]):
    old = get_query_params()
    old.clear()
    old.update(params)


def get_session_state():
    try:
        return _local._session_state
    except AttributeError:
        _local._session_state = {}
        return _local._session_state


def set_session_state(state: dict[str, typing.Any]):
    old = get_session_state()
    old.clear()
    old.update(state)


Style = dict[str, str | None]


class RenderTreeNode(BaseModel):
    name: str
    props: dict[str, typing.Any] = {}
    children: list["RenderTreeNode"] = []
    style: Style = {}

    def mount(self) -> "RenderTreeNode":
        _local._render_root.children.append(self)
        return self


class NestingCtx:
    def __init__(self, node: RenderTreeNode = None):
        self.node = node or _local._render_root
        self.parent = None

    def __enter__(self):
        # global local._render_root
        try:
            self.parent = _local._render_root
        except AttributeError:
            pass
        _local._render_root = self.node

    def __exit__(self, exc_type, exc_val, exc_tb):
        # global local._render_root
        _local._render_root = self.parent

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
                    state=get_session_state().copy(),
                    query_params=get_query_params().copy(),
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
