from gooey_gui import core
from gooey_gui.components import common as gui


class AlertDialogRef:
    def __init__(self, key: str, is_open: bool = False):
        self.key = key
        self.is_open = is_open

    def set_open(self, value: bool):
        self.is_open = core.session_state[self.key] = value

    @property
    def open_btn_key(self):
        return self.key + ":open"

    @property
    def close_btn_key(self):
        return self.key + ":close"


class ConfirmDialogRef(AlertDialogRef):
    pressed_confirm: bool = False

    @classmethod
    def from_alert_dialog(cls, ref: AlertDialogRef) -> "ConfirmDialogRef":
        return cls(key=ref.key, is_open=ref.is_open)

    @property
    def confirm_btn_key(self):
        return self.key + ":confirm"


def use_confirm_dialog(
    key: str,
    close_on_confirm: bool = True,
) -> ConfirmDialogRef:
    ref = ConfirmDialogRef.from_alert_dialog(use_alert_dialog(key))
    if not ref.is_open:
        return ref

    ref.pressed_confirm = bool(core.session_state.pop(ref.confirm_btn_key, None))
    if ref.pressed_confirm and close_on_confirm:
        ref.set_open(False)

    return ref


def use_alert_dialog(key: str) -> AlertDialogRef:
    ref = AlertDialogRef(key=key, is_open=bool(core.session_state.get(key)))
    if core.session_state.pop(ref.close_btn_key, None):
        ref.set_open(False)
    return ref


def alert_dialog(
    ref: AlertDialogRef,
    modal_title: str,
    large: bool = False,
    unsafe_allow_html: bool = False,
) -> core.NestingCtx:
    header, body, _ = modal_scaffold(large=large)
    with header:
        with gui.div():
            gui.write(modal_title, unsafe_allow_html=unsafe_allow_html)
        gui.button(
            '<i class="fa fa-times fa-xl">',
            key=ref.close_btn_key,
            type="tertiary",
            className="m-0 py-1 px-2",
        )
    return body


def button_with_confirm_dialog(
    *,
    ref: ConfirmDialogRef,
    trigger_label: str,
    modal_title: str,
    modal_content: str | None = None,
    cancel_label: str = "Cancel",
    confirm_label: str,
    trigger_className: str = "",
    trigger_type: str = "secondary",
    cancel_className: str = "",
    confirm_className: str = "",
    large: bool = False,
) -> core.NestingCtx:
    if gui.button(
        label=trigger_label,
        key=ref.open_btn_key,
        className=trigger_className,
        type=trigger_type,
    ):
        ref.set_open(True)
    if ref.is_open:
        return confirm_dialog(
            ref=ref,
            modal_title=modal_title,
            modal_content=modal_content,
            cancel_label=cancel_label,
            confirm_label=confirm_label,
            cancel_className=cancel_className,
            confirm_className=confirm_className,
            large=large,
        )
    return gui.dummy()


def confirm_dialog(
    *,
    ref: ConfirmDialogRef,
    modal_title: str,
    modal_content: str | None = None,
    cancel_label: str = "Cancel",
    confirm_label: str,
    cancel_className: str = "",
    confirm_className: str = "",
    large: bool = False,
) -> core.NestingCtx:
    header, body, footer = modal_scaffold(large=large)
    with header:
        gui.write(modal_title)
    with footer:
        gui.button(
            label=cancel_label,
            key=ref.close_btn_key,
            className=cancel_className,
            type="tertiary",
        )
        gui.button(
            label=confirm_label,
            key=ref.confirm_btn_key,
            type="primary",
            className=confirm_className,
        )
    if modal_content:
        with body:
            gui.write(modal_content)
    return body


def modal_scaffold(
    large: bool = False,
) -> tuple[core.NestingCtx, core.NestingCtx, core.NestingCtx]:
    if large:
        large_cls = "modal-lg"
    else:
        large_cls = ""
    with core.current_root_ctx():
        with (
            gui.div(
                className="modal d-block",
                style=dict(zIndex="9999"),
                tabIndex="-1",
                role="dialog",
            ),
            gui.div(
                className=f"modal-dialog modal-dialog-centered {large_cls}",
                role="document",
            ),
            gui.div(className="modal-content border-0 shadow"),
        ):
            return (
                gui.div(className="modal-header border-0"),
                gui.div(className="modal-body"),
                gui.div(className="modal-footer border-0 py-0"),
            )
