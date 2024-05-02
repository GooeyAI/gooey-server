import gooey_ui as st
from daras_ai_v2.field_render import field_label_val

from daras_ai_v2.lipsync_api import LipsyncModel, SadTalkerSettings


def lipsync_settings(selected_model: str):
    match selected_model:
        case LipsyncModel.Wav2Lip.name:
            wav2lip_settings()
            st.session_state.pop("sadtalker_settings", None)
        case LipsyncModel.SadTalker.name:
            settings = SadTalkerSettings.parse_obj(
                st.session_state.setdefault(
                    "sadtalker_settings", SadTalkerSettings().dict()
                )
            )
            sadtalker_settings(settings)
            st.session_state["sadtalker_settings"] = settings.dict()


def sadtalker_settings(settings: SadTalkerSettings):
    settings.still = st.checkbox(
        **field_label_val(settings, "still"),
    )

    settings.preprocess = st.selectbox(
        **field_label_val(settings, "preprocess"),
        options=SadTalkerSettings.schema()["properties"]["preprocess"]["enum"],
    )

    settings.pose_style = st.slider(
        **field_label_val(settings, "pose_style"),
        min_value=0,
        max_value=45,
    )

    settings.expression_scale = st.number_input(
        **field_label_val(settings, "expression_scale"),
    )

    # st.selectbox("Face Enhancer", [None, "gfpgan", "RestoreFormer"], value=settings.enhancer)
    # st.selectbox("Background Enhancer", [None, "realesrgan"], value=settings.background_enhancer)

    settings.ref_eyeblink = (
        st.file_uploader(
            **field_label_val(settings, "ref_eyeblink"),
            accept=[".mp4"],
        )
        or None
    )

    settings.ref_pose = (
        st.file_uploader("Reference Pose", value=settings.ref_pose, accept=[".mp4"])
        or None
    )

    input_yaw = st.text_input(
        "Input Yaw (comma separated)",
        value=", ".join(map(str, settings.input_yaw or [])),
    )
    try:
        settings.input_yaw = (
            list(map(int, filter(None, input_yaw.strip().split(",")))) or None
        )
    except ValueError:
        settings.input_yaw = None
        st.error("Please enter comma separated integers for Input Yaw")

    input_pitch = st.text_input(
        "Input Pitch (comma separated)",
        value=", ".join(map(str, settings.input_pitch or [])),
    )
    try:
        settings.input_pitch = (
            list(map(int, filter(None, input_pitch.strip().split(",")))) or None
        )
    except ValueError:
        settings.input_pitch = None
        st.error("Please enter comma separated integers for Input Pitch")

    input_roll = st.text_input(
        "Input Roll (comma separated)",
        value=", ".join(map(str, settings.input_roll or [])),
    )
    try:
        settings.input_roll = (
            list(map(int, filter(None, input_roll.strip().split(",")))) or None
        )
    except ValueError:
        settings.input_roll = None
        st.error("Please enter comma separated integers for Input Roll")


def wav2lip_settings():
    st.write("##### ⌖ Lipsync Face Padding")
    st.caption(
        "Adjust the detected face bounding box. Often leads to improved results. Recommended to give at least 10 padding for the chin region."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.slider(
            "Head",
            min_value=0,
            max_value=50,
            key="face_padding_top",
        )
    with col2:
        st.slider(
            "Chin",
            min_value=0,
            max_value=50,
            key="face_padding_bottom",
        )
    with col3:
        st.slider(
            "Left Cheek",
            min_value=0,
            max_value=50,
            key="face_padding_left",
        )
    with col4:
        st.slider(
            "Right Cheek",
            min_value=0,
            max_value=50,
            key="face_padding_right",
        )
