import gooey_ui as st
from enum import Enum


class LipsyncModel(Enum):
    Wav2Lip = "Wav2Lip"
    SadTalker = "SadTalker"


def lipsync_settings():
    model = st.selectbox(
        "Select the Lipsync Model",
        LipsyncModel._member_names_,
        key="lipsync_model",
        format_func=lambda x: LipsyncModel[x].value,  # type: ignore
    )
    if model == LipsyncModel.Wav2Lip.name:
        wav2lip_settings()
    elif model == LipsyncModel.SadTalker.name:
        sadtalker_settings()


def sadtalker_settings():
    st.session_state.setdefault("pose_style", 0)
    st.slider("Pose Style", min_value=0, max_value=45, key="pose_style")
    st.file_uploader("Reference Eyeblink", key="ref_eyeblink", accept=[".mp4"])
    if not st.session_state.get("ref_eyeblink"):
        st.session_state["ref_eyeblink"] = None
    st.file_uploader("Reference Pose", key="ref_pose", accept=[".mp4"])
    if not st.session_state.get("ref_pose"):
        st.session_state["ref_pose"] = None
    st.session_state.setdefault("batch_size", 2)
    st.number_input("Batch Size", min_value=1, key="batch_size")
    st.session_state.setdefault("size", 256)
    st.number_input("Image Size", min_value=1, key="size")
    st.session_state.setdefault("expression_scale", 1.0)
    st.number_input("Expression Scale", key="expression_scale")
    st.session_state["__input_yaw"] = ",".join(st.session_state.get("input_yaw") or [])
    input_yaw = st.text_input("Input Yaw (comma separated)", key="__input_yaw")
    st.session_state["input_yaw"] = (
        list(map(int, input_yaw.split(","))) if input_yaw.strip() else None
    )
    st.session_state["__input_pitch"] = ",".join(
        st.session_state.get("input_pitch") or []
    )
    input_pitch = st.text_input("Input Pitch (comma separated)", key="__input_pitch")
    st.session_state["input_pitch"] = (
        list(map(int, input_pitch.split(","))) if input_pitch.strip() else None
    )
    st.session_state["__input_roll"] = ",".join(
        st.session_state.get("input_roll") or []
    )
    input_roll = st.text_input("Input Roll (comma separated)", key="__input_roll")
    st.session_state["input_roll"] = (
        list(map(int, input_roll.split(","))) if input_roll.strip() else None
    )
    st.selectbox("Face Enhancer", [None, "gfpgan", "RestoreFormer"], key="enhancer")
    st.selectbox("Background Enhancer", [None, "realesrgan"], key="background_enhancer")
    st.checkbox("Generate 3D Face and 3D Landmarks", key="face3dvis")
    st.checkbox("Still (fewer head motion, works with preprocess 'full')", key="still")
    st.selectbox(
        "Preprocess",
        ["crop", "extcrop", "resize", "full", "extfull"],
        key="preprocess",
    )


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
