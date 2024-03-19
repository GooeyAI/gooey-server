import typing

import gooey_ui as st


def grid_layout(
    column_spec,
    iterable: typing.Iterable,
    render,
    separator=True,
    column_props: dict[str, typing.Any] | None = None,
):
    # make a copy so it can be modified
    column_props = dict(column_props or {})
    extra_classes = column_props.pop("className", "mb-4 pb-2")

    for item, col in zip(iterable, infinte_cols(column_spec)):
        if separator:
            col.node.props["className"] += f" border-bottom " + extra_classes
            col.node.props.update(column_props)
        with col:
            render(item)


def infinte_cols(spec):
    while True:
        yield from st.columns(spec)
