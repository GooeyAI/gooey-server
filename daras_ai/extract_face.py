import numpy as np

from daras_ai_v2.exceptions import UserError


def extract_and_reposition_face_cv2(
    orig_img,
    *,
    out_size: (int, int) = (512, 512),
    out_face_scale: float = 0.2,
    out_pos_x: float = 4 / 9,
    out_pos_y: float = 3 / 9,
):
    import cv2

    img_y, img_x, _ = orig_img.shape
    out_img_x, out_img_y = out_size
    out_img_shape = (out_img_y, out_img_x, orig_img.shape[-1])

    # blank mask for the original img
    orig_mask = np.zeros(orig_img.shape, dtype=np.uint8)

    for face_vertices in face_oval_hull_generator(orig_img):
        # draw face mask for the original img
        cv2.fillConvexPoly(orig_mask, face_vertices, (255, 255, 255))

        # face polygon vertices x & y coords
        face_hull_x = face_vertices[:, :, 0]
        face_hull_y = face_vertices[:, :, 1]

        # original face height
        face_height = abs(face_hull_y.max() - face_hull_y.min())

        # image resize ratio
        re_ratio = (out_img_y / face_height) * out_face_scale

        # resized image size
        re_img_x = int(img_x * re_ratio)
        re_img_y = int(img_y * re_ratio)

        # resized image and mask
        re_img = cv2.resize(orig_img, (re_img_x, re_img_y))
        re_mask = cv2.resize(orig_mask, (re_img_x, re_img_y))

        # face center coords in original image
        face_center_x = (face_hull_x.max() + face_hull_x.min()) // 2
        face_center_y = (face_hull_y.max() + face_hull_y.min()) // 2

        # face center coords in resized image
        re_face_center_x = int(face_center_x * re_ratio)
        re_face_center_y = int(face_center_y * re_ratio)

        # crop of resized image
        re_crop_x1 = int(max(re_face_center_x - (out_img_x * out_pos_x), 0))
        re_crop_y1 = int(max(re_face_center_y - (out_img_y * out_pos_y), 0))

        re_crop_x2 = int(
            min(re_face_center_x + (out_img_x * (1 - out_pos_x)), re_img_x)
        )
        re_crop_y2 = int(
            min(re_face_center_y + (out_img_y * (1 - out_pos_y)), re_img_y)
        )

        # crop of output image
        out_crop_x1 = int((out_img_x * out_pos_x) - (re_face_center_x - re_crop_x1))
        out_crop_y1 = int((out_img_y * out_pos_y) - (re_face_center_y - re_crop_y1))

        re_crop_width = re_crop_x2 - re_crop_x1
        re_crop_height = re_crop_y2 - re_crop_y1

        out_crop_x2 = out_crop_x1 + re_crop_width
        out_crop_y2 = out_crop_y1 + re_crop_height

        # efficient croppers / slicers
        re_rect_cropper = (
            slice(re_crop_y1, re_crop_y2),
            slice(re_crop_x1, re_crop_x2),
            slice(0, 3),
        )
        out_rect_cropper = (
            slice(out_crop_y1, out_crop_y2),
            slice(out_crop_x1, out_crop_x2),
            slice(0, 3),
        )

        out_img = np.zeros(out_img_shape, dtype=np.uint8)
        out_mask = np.zeros(out_img_shape, dtype=np.uint8)

        # paste crop of resized image onto the crop of output image
        out_img[out_rect_cropper] = re_img[re_rect_cropper]
        out_mask[out_rect_cropper] = re_mask[re_rect_cropper]

        return out_img, out_mask


def extract_face_cv2(image_cv2):
    import cv2

    face_mask = np.zeros(image_cv2.shape, dtype=np.uint8)
    for face_oval_hull in face_oval_hull_generator(image_cv2):
        cv2.fillConvexPoly(face_mask, face_oval_hull, (255, 255, 255))
    return face_mask


def face_oval_hull_generator(image_cv2):
    import mediapipe as mp
    import cv2

    mp_face_mesh = mp.solutions.face_mesh

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
            raise UserError("Face not found")

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
    import mediapipe as mp

    mp_drawing = mp.solutions.drawing_utils

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
