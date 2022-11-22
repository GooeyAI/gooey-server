import cv2
import numpy as np

from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes


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


def overlay_rule_of_3rds(img):
    """draw rule of 3rds grid on an image"""
    color = (200, 200, 200)
    stroke = 2
    img_y, img_x, _ = img.shape
    for i in range(2):
        pos = (img_y // 3) * (i + 1)
        cv2.line(img, (0, pos), (img_x, pos), color, stroke)

        pos = (img_x // 3) * (i + 1)
        cv2.line(img, (pos, 0), (pos, img_y), color, stroke)
