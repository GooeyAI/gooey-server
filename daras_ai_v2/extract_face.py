import cv2
import mediapipe as mp
import numpy as np

from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes
from daras_ai_v2.repositioning import reposition_object

mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


def extract_face_img_bytes(
    img_bytes: bytes,
    out_size: (int, int),
    face_scale: float,
    pos_x: float,
    pos_y: float,
) -> (bytes, bytes):
    image_cv2 = bytes_to_cv2_img(img_bytes)
    image_cv2, face_mask_cv2 = extract_and_reposition_face_cv2(
        image_cv2,
        out_size=out_size,
        out_face_scale=face_scale,
        out_pos_x=pos_x,
        out_pos_y=pos_y,
    )

    # smooth out the sharp edges
    face_mask_cv2 = cv2.GaussianBlur(face_mask_cv2, (0, 0), 5)

    image_bytes = cv2_img_to_bytes(image_cv2)
    face_mask_bytes = cv2_img_to_bytes(face_mask_cv2)
    return image_bytes, face_mask_bytes


def rgb_img_to_rgba(
    img_bytes: bytes,
    mask_bytes: bytes = None,
    alpha: float = 1.0,
) -> bytes:
    img_cv2 = bytes_to_cv2_img(img_bytes)
    alpha_mask_shape = (img_cv2.shape[0], img_cv2.shape[1], 1)
    strength_int = int(255 * alpha)
    if mask_bytes:
        mask_cv2 = bytes_to_cv2_img(mask_bytes)
        alpha_mask = mask_cv2[:, :, 0] > 0
        alpha_mask = alpha_mask.reshape(alpha_mask_shape) * strength_int
    else:
        alpha_mask = np.ones(alpha_mask_shape) * strength_int
    ret_img_cv2 = np.append(img_cv2, alpha_mask, axis=2)
    return cv2_img_to_bytes(ret_img_cv2)


def extract_and_reposition_face_cv2(
    orig_img,
    *,
    out_size: (int, int) = (512, 512),
    out_face_scale: float = 0.2,
    out_pos_x: float = 4 / 9,
    out_pos_y: float = 3 / 9,
):
    # blank mask for the original img
    orig_mask = np.zeros(orig_img.shape, dtype=np.uint8)

    for face_vertices in face_oval_hull_generator(orig_img):
        # draw face mask for the original img
        cv2.fillConvexPoly(orig_mask, face_vertices, (255, 255, 255))

        return reposition_object(
            orig_img=orig_img,
            orig_mask=orig_mask,
            out_size=out_size,
            out_obj_scale=out_face_scale,
            out_pos_x=out_pos_x,
            out_pos_y=out_pos_y,
        )


def extract_face_cv2(image_cv2):
    face_mask = np.zeros(image_cv2.shape, dtype=np.uint8)
    for face_oval_hull in face_oval_hull_generator(image_cv2):
        cv2.fillConvexPoly(face_mask, face_oval_hull, (255, 255, 255))
    return face_mask


def face_oval_hull_generator(image_cv2):
    image_rows, image_cols, _ = image_cv2.shape

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        refine_landmarks=True,
        max_num_faces=10,
        min_detection_confidence=0.5,
    ) as face_mesh:
        # Convert the BGR image to RGB and process it with MediaPipe Face Mesh.
        results = face_mesh.process(cv2.cvtColor(image_cv2, cv2.COLOR_BGR2RGB))

        if not results.multi_face_landmarks:
            raise ValueError("Face not found")

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
            yield face_oval_hull


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
