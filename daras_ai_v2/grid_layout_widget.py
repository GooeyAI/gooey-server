import typing

import streamlit as st


def _default_sep():
    st.write("---")


def grid_layout(column_spec, iterable: typing.Iterable, render, separator=_default_sep):
    it = iter(iterable)
    while True:
        for col in st.columns(column_spec):
            with col:
                while True:
                    try:
                        item = next(it)
                    except StopIteration:
                        # rendered all items, exit
                        return
                    try:
                        render(item)
                    except SkipIteration:
                        # render next item in same col
                        continue
                    else:
                        # render next item in next col
                        break
        if separator:
            separator()


class SkipIteration(Exception):
    pass
