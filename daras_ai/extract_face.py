import cv2
import mediapipe as mp
import numpy as np
import requests
import streamlit as st

from daras_ai.core import daras_ai_step_computer, daras_ai_step_config
from daras_ai.image_input import (
    cv2_img_to_png,
    upload_file_from_bytes,
    bytes_to_cv2_img,
)

mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


@daras_ai_step_config("Extract Face")
def extract_face(idx, state, variables):
    selected_model = st.selectbox("Model", options=["MediaPipe"])
    state.update({"selected_model": selected_model})

    input_img_var = st.text_input(
        "Input Image Variable",
        value=state.get("input_img_var", ""),
        help=f"face image input var {idx}",
    )
    state.update({"input_img_var": input_img_var})

    face_mask_var = st.text_input(
        "Face Mask Output Variable",
        value=state.get("face_mask_var", ""),
        help=f"face mask output var {idx}",
    )
    state.update({"face_mask_var": face_mask_var})

    face_cutout_var = st.text_input(
        "Face Cutout Output Variable (optional)",
        value=state.get("face_cutout_var", ""),
        help=f"face cutout output var {idx}",
    )
    state.update({"face_cutout_var": face_cutout_var})


@daras_ai_step_computer
def extract_face(idx, state, variables):
    input_img = variables.get(state["input_img_var"])
    selected_model = state["selected_model"]
    face_mask_var = state["face_mask_var"]
    face_cutout_var = state["face_cutout_var"]

    if not input_img:
        raise ValueError

    r = requests.get(input_img)
    r.raise_for_status()
    input_img_bytes = r.content

    if not (selected_model and input_img and face_mask_var and input_img_bytes):
        raise ValueError

    match selected_model:
        case "MediaPipe":
            image_cv2 = bytes_to_cv2_img(input_img_bytes)

            face_mask = extract_face_cv2(image_cv2)

            variables[face_mask_var] = upload_file_from_bytes(
                "face_mask.png",
                cv2_img_to_png(face_mask),
            )

            if face_cutout_var:
                # gaussian = np.random.normal(0, 1, image_cv2.shape).astype(np.uint8)
                # gaussian = (np.ones(image_cv2.shape) * 255).astype(np.uint8)
                variables[face_cutout_var] = upload_file_from_bytes(
                    "face_cutout.png",
                    # img_to_png((gaussian & ~face_mask) + (image_cv2 & face_mask)),
                    cv2_img_to_png((image_cv2 & face_mask)),
                )


def extract_face_cv2(image):
    face_mask = np.zeros(image.shape, dtype=np.uint8)

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        refine_landmarks=True,
        max_num_faces=10,
        min_detection_confidence=0.5,
    ) as face_mesh:
        # Convert the BGR image to RGB and process it with MediaPipe Face Mesh.
        results = face_mesh.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

        if not results.multi_face_landmarks:
            raise ValueError("Face not found")

        image_rows, image_cols, _ = image.shape

        for landmark_list in results.multi_face_landmarks:
            idx_to_coordinates = build_idx_to_coordinates_dict(
                image_cols, image_rows, landmark_list
            )

            face_oval_points = []
            for start_idx, end_idx in mp_face_mesh.FACEMESH_FACE_OVAL:
                if start_idx in idx_to_coordinates and end_idx in idx_to_coordinates:
                    for idx in start_idx, end_idx:
                        face_oval_points.append(idx_to_coordinates[idx])

            face_oval_hull = cv2.convexHull(np.array(face_oval_points))

            cv2.fillConvexPoly(face_mask, face_oval_hull, (255, 255, 255))

    return face_mask


def build_idx_to_coordinates_dict(image_cols, image_rows, landmark_list):
    """
    Stolen from mediapipe.solutions.drawing_utils.draw_landmarks()
    """
    idx_to_coordinates = {}
    for idx, landmark in enumerate(landmark_list.landmark):
        if (
            landmark.HasField("visibility")
            and landmark.visibility < mp_drawing._VISIBILITY_THRESHOLD
        ) or (
            landmark.HasField("presence")
            and landmark.presence < mp_drawing._PRESENCE_THRESHOLD
        ):
            continue
        landmark_px = mp_drawing._normalized_to_pixel_coordinates(
            landmark.x, landmark.y, image_cols, image_rows
        )
        if landmark_px:
            idx_to_coordinates[idx] = landmark_px
    return idx_to_coordinates
