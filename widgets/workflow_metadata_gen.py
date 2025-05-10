from typing import Optional

import gooey_gui as gui

from daras_ai_v2 import icons


def render_ai_generated_image_widget(
    *,
    image_url: Optional[str],
    key: str,
    is_generating: bool,
    error_msg: Optional[str],
    icon: str,
    is_circle_image: bool = False,
) -> bool:
    """
    Renders a reusable AI-generated image widget with preview, error, upload, and action buttons.
    """
    if error_msg:
        error_dialog_ref = gui.use_alert_dialog(key=key + ":error-dialog")
        with gui.alert_dialog(ref=error_dialog_ref, modal_title="### Error"):
            with gui.tag("code"):
                gui.write(error_msg, className="text-danger")
            gui.write("Please try again or upload an image manually.")

    upload_dialog_ref = gui.use_alert_dialog(key=key + ":upload-dialog")
    if image_url:
        upload_dialog_ref.set_open(False)
    if upload_dialog_ref.is_open:
        with gui.alert_dialog(ref=upload_dialog_ref, modal_title="### Upload Image"):
            gui.file_uploader("", accept=["image/*"], key=key)

    if image_url:
        img_style = dict(
            backgroundImage=f"url({image_url})",
            backgroundSize="cover",
            backgroundPosition="center",
        )
    else:
        img_style = dict()

    img_classes = "d-flex align-items-center justify-content-center bg-light b-1 border"
    if is_circle_image:
        img_classes += " rounded-circle"
    else:
        img_classes += " rounded"

    with gui.div(
        style=dict(height="200px", width="200px") | img_style,
        className=img_classes,
    ):
        if is_generating:
            with gui.styled(
                """
                &.generating_image_spinner i {
                    animation: spin 0.7s ease-in-out infinite;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
                """
            ):
                gui.write(
                    f"## {icons.stars}",
                    className="text-muted generating_image_spinner",
                    unsafe_allow_html=True,
                )
        elif not image_url:
            gui.write(f"# {icon}", className="text-muted", unsafe_allow_html=True)

    with gui.div(
        className="d-flex align-items-md-center align-items-start justify-content-center gap-1 flex-md-row flex-column text-nowrap"
    ):
        if is_generating:
            gui.button(
                f"{icons.sparkles} Generating...",
                type="tertiary",
                disabled=True,
            )
        elif image_url:
            if gui.button(f"{icons.clear} Clear", type="tertiary"):
                gui.session_state[key] = ""
                raise gui.RerunException()
            gui.download_button(
                f"{icons.download_solid} Download", image_url, type="tertiary"
            )
        else:
            if gui.button(f"{icons.upload} Upload", type="tertiary"):
                upload_dialog_ref.set_open(True)
                raise gui.RerunException()
            if gui.button(f"{icons.sparkles} Generate", type="tertiary"):
                return True

    return False
