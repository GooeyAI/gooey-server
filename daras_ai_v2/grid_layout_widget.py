import typing

import gooey_ui as st


def grid_layout(column_spec, iterable: typing.Iterable, render, separator=True):
    it = iter(iterable)
    while True:
        for col in st.columns(column_spec):
            if separator:
                col.node.props["className"] += " border-bottom mb-4 pb-2"
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


class SkipIteration(Exception):
    pass
