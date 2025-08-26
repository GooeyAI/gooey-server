import typing
import gooey_gui as gui


def switch_with_section(
    label: str,
    key: str = None,
    help: str | None = None,
    tooltip_placement: str | None = None,
    *,
    disabled: bool = False,
    size: str = "large",
    label_visibility: str = "visible",
    control_keys: typing.Iterable[str] = (),
    render_section: typing.Callable | None = None,
    title_class: str = "bg-light px-1 pb-1 pt-0 rounded my-2",
    section_class: str = "bg-white rounded px-2",
    **props,
):
    with gui.div(className=title_class):
        enabled = gui.switch(
            label=label,
            value=any(gui.session_state.get(k) for k in control_keys),
            key=key,
            help=help,
            tooltip_placement=tooltip_placement,
            disabled=disabled,
            size=size,
            label_visibility=label_visibility,
            className=" p-1",
            **props,
        )
        if enabled and render_section:
            with gui.div(className=section_class):
                render_section()
    return enabled
