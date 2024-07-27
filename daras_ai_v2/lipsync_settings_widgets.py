import gooey_gui as gui
from daras_ai_v2.field_render import field_label_val

from daras_ai_v2.lipsync_api import LipsyncModel, SadTalkerSettings


def lipsync_settings(selected_model: str):
    match selected_model:
        case LipsyncModel.Wav2Lip.name:
            wav2lip_settings()
            gui.session_state.pop("sadtalker_settings", None)
        case LipsyncModel.SadTalker.name:
            settings = SadTalkerSettings.parse_obj(
                gui.session_state.setdefault(
                    "sadtalker_settings", SadTalkerSettings().dict()
                )
            )
            sadtalker_settings(settings)
            gui.session_state["sadtalker_settings"] = settings.dict()


def sadtalker_settings(settings: SadTalkerSettings):
    settings.still = gui.checkbox(
        **field_label_val(settings, "still"),
    )

    settings.preprocess = gui.selectbox(
        **field_label_val(settings, "preprocess"),
        options=SadTalkerSettings.schema()["properties"]["preprocess"]["enum"],
    )

    settings.pose_style = gui.slider(
        **field_label_val(settings, "pose_style"),
        min_value=0,
        max_value=45,
    )

    settings.expression_scale = gui.number_input(
        **field_label_val(settings, "expression_scale"),
    )

    settings.ref_eyeblink = (
        gui.file_uploader(
            **field_label_val(settings, "ref_eyeblink"),
            accept=[".mp4"],
        )
        or None
    )

    settings.ref_pose = (
        gui.file_uploader(
            **field_label_val(settings, "ref_pose"),
            accept=[".mp4"],
        )
        or None
    )


def wav2lip_settings():
    gui.write("##### ⌖ Lipsync Face Padding")
    gui.caption(
        "Adjust the detected face bounding box. Often leads to improved results. Recommended to give at least 10 padding for the chin region."
    )

    col1, col2, col3, col4 = gui.columns(4)
    with col1:
        gui.slider(
            "Head",
            min_value=0,
            max_value=50,
            key="face_padding_top",
        )
    with col2:
        gui.slider(
            "Chin",
            min_value=0,
            max_value=50,
            key="face_padding_bottom",
        )
    with col3:
        gui.slider(
            "Left Cheek",
            min_value=0,
            max_value=50,
            key="face_padding_left",
        )
    with col4:
        gui.slider(
            "Right Cheek",
            min_value=0,
            max_value=50,
            key="face_padding_right",
        )
