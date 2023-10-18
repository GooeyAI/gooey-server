import typing

import gooey_ui as st


def grid_layout(column_spec, iterable: typing.Iterable, render, separator=True):
    for item, col in zip(iterable, infinte_cols(column_spec)):
        if separator:
            col.node.props["className"] += " border-bottom mb-4 pb-2"
        with col:
            render(item)


def infinte_cols(spec):
    while True:
        yield from st.columns(spec)
