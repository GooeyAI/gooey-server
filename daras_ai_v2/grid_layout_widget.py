import typing

import gooey_gui as gui

SEPARATOR_STYLE = """
@media (max-width: 991px) {
    & > :not(:last-of-type)::after {
        content: "";
        width: 100%;
        display: block;
        margin: 1rem 0;
        border-bottom: 1px solid #dee2e6;
    }
}

&:not(:last-of-type)::after {
    content: "";
    width: 100%;
    margin: 1rem 0.75rem;
    border-bottom: 1px solid #dee2e6;
}
"""


def grid_layout(
    column_spec,
    iterable: typing.Iterable,
    render,
    separator=True,
):
    if separator:
        parent = gui.styled(SEPARATOR_STYLE)
    else:
        parent = gui.dummy()
    with parent:
        for item, col in zip(iterable, infinte_cols(column_spec)):
            with col:
                render(item)


def infinte_cols(spec):
    while True:
        yield from gui.columns(spec)
