import gooey_gui as gui

from daras_ai_v2.html_spinner_widget import html_spinner


def confirm_modal(
    *,
    title: str,
    key: str,
    text: str,
    button_label: str,
    button_class: str = "",
    text_on_confirm: str | None = None,
) -> tuple[gui.Modal, bool]:
    modal = gui.Modal(title, key=key)
    confirmed_key = f"{key}-confirmed"
    if modal.is_open():
        with modal.container():
            with gui.div(className="pt-4 pb-3"):
                gui.write(text)
            with gui.div(className="d-flex w-100 justify-content-end"):
                confirmed = bool(gui.session_state.get(confirmed_key, None))
                if confirmed and text_on_confirm:
                    html_spinner(text_on_confirm)
                else:
                    if gui.button(
                        "Cancel",
                        type="tertiary",
                        className="me-2",
                        key=f"{key}-cancelled",
                    ):
                        modal.close()
                    confirmed = gui.button(
                        button_label,
                        type="primary",
                        key=confirmed_key,
                        className=button_class,
                    )
                return modal, confirmed
    else:
        gui.session_state.pop(confirmed_key, None)
    return modal, False
