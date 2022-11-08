import numpy as np

from daras_ai.extract_face import extract_and_reposition_face_cv2
from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes


import cv2


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


def rgb_mask_to_rgba(mask_bytes: bytes) -> bytes:
    """Produces an image whose fully transparent areas (e.g. where alpha is zero) indicate where the mask is."""
    mask_cv2 = bytes_to_cv2_img(mask_bytes)
    binary_mask = mask_cv2[:, :, 0] > 0
    binary_mask = binary_mask.reshape((*binary_mask.shape, 1))
    ret_mask_cv2 = np.zeros(mask_cv2.shape, dtype=np.uint8)
    ret_mask_cv2 = np.append(ret_mask_cv2, binary_mask, axis=2)
    return cv2_img_to_bytes(ret_mask_cv2)
