import numpy as np

from daras_ai.extract_face import extract_and_reposition_face_cv2
from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes


def extract_face_img_bytes(
    img_bytes: bytes,
    out_size: (int, int),
    face_scale: float,
    pos_x: float,
    pos_y: float,
) -> (bytes, bytes):
    import cv2

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
