import sys
import types
import typing
from functools import partial
from textwrap import dedent

import streamlit
from pydantic import BaseModel


class RenderTreeElement(BaseModel):
    name: str
    args: list[typing.Any] = []
    kwargs: dict[str, typing.Any] = {}
    repr: str = ""
    children: list["RenderTreeElement"] = []
    style: str = ""


RenderTree = list[RenderTreeElement]


class Context:
    render_tree: RenderTree = []


class Base:
    def __init__(self, name, elem=None):
        self.name: str = name
        self.elem: RenderTreeElement = elem

    def __repr__(self):
        return f"{self.__class__}<{self.name}>"


def format_argstr(args, kwargs):
    return ", ".join(list(map(repr, args)) + [f"{k}={v!r}" for k, v in kwargs.items()])


def pretty_call_repr(name, args, kwargs):
    argstr = format_argstr(args, kwargs)
    call_repr = f"{name}({argstr})"
    return call_repr


class StComponentMock(Base):
    def __getattr__(self, item):
        return self.__class__(f"{self.name}.{item}")

    def option_menu(self, *args, options, **kwargs):
        return options[0]

    def tabs(self, names):
        args = [names]
        call_repr = pretty_call_repr(self.name, args, {})
        # print(">", call_repr)
        elem = RenderTreeElement(
            name="st.tabs",
            args=args,
            repr=call_repr,
        )
        Context.render_tree.append(elem)
        tabs = [
            RenderTreeElement(
                name="st.tab",
                kwargs={"title": title},
                repr=f"st.tab({title=})",
            )
            for title in names
        ]
        elem.children = tabs
        return [self.__class__("st.tab", col) for col in tabs]

    def columns(self, spec, gap="medium"):
        if isinstance(spec, int):
            spec = [1] * spec
        args = [spec]
        call_repr = pretty_call_repr(self.name, args, {})
        # print(">", call_repr)
        elem = RenderTreeElement(
            name="st.columns",
            args=args,
            repr=call_repr,
        )
        Context.render_tree.append(elem)
        total_weight = sum(spec)
        columns = [
            RenderTreeElement(
                name="st.column",
                kwargs={"width": width},
                repr=f"st.column({width=})",
            )
            for w in spec
            if (width := f"{w / total_weight * 100:.2f}%")
        ]
        elem.children = columns
        return [self.__class__("st.column", col) for col in columns]

    def __call__(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            args = (dedent(args[0]).strip(),) + args[1:]
        call_repr = pretty_call_repr(self.name, args, kwargs)
        # print(">", call_repr)
        elem = RenderTreeElement(
            name=self.name,
            args=args,
            kwargs=kwargs,
            repr=call_repr,
        )
        Context.render_tree.append(elem)
        return self.__class__(call_repr, elem)

    def __getitem__(self, item):
        __repr__ = f"{self.name}[{item!r}]"
        # print(f"> {__repr__}")
        return self.__class__(__repr__)

    def __enter__(self, *args, **kwargs):
        self._parent = Context.render_tree
        Context.render_tree = self.elem.children
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        Context.render_tree = self._parent
        del self._parent
        return False

    def button(self, *args, **kwargs):
        return False


class StMock(StComponentMock, types.ModuleType):
    def stop(self):
        exit(0)

    def experimental_get_query_params(self):
        return self._query_params

    # _query_params = {}
    _query_params = {"page_slug": ["video-bots"]}
    session_state = {}
    render_tree = Context.render_tree

    def cache_data(self, fn=None, *args, **kwargs):
        if not fn:
            return partial(self.cache_data, *args, **kwargs)
        return fn

    def cache_resource(self, fn=None, *args, **kwargs):
        if not fn:
            return partial(self.cache_resource, *args, **kwargs)
        return fn


sys.modules["streamlit2"] = StMock("st")
