import cv2
import numpy as np

from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes


def reposition_object_img_bytes(
    *,
    img_bytes: bytes,
    mask_bytes: bytes,
    out_size: (int, int) = (512, 512),
    out_obj_scale: float = 0.2,
    out_pos_x: float = 4 / 9,
    out_pos_y: float = 3 / 9,
) -> (bytes, bytes):
    image_cv2 = bytes_to_cv2_img(img_bytes)
    mask_cv2 = bytes_to_cv2_img(mask_bytes)
    image_cv2, mask_cv2 = reposition_object(
        orig_img=image_cv2,
        orig_mask=mask_cv2,
        out_size=out_size,
        out_obj_scale=out_obj_scale,
        out_pos_x=out_pos_x,
        out_pos_y=out_pos_y,
    )

    # smooth out the sharp edges - maybe doesn't work too well for objects?
    # face_mask_cv2 = cv2.GaussianBlur(face_mask_cv2, (0, 0), 5)

    image_bytes = cv2_img_to_bytes(image_cv2)
    face_mask_bytes = cv2_img_to_bytes(mask_cv2)
    return image_bytes, face_mask_bytes


def reposition_object(
    *,
    orig_img,
    orig_mask,
    out_size: (int, int) = (512, 512),
    out_obj_scale: float = 0.2,
    out_pos_x: float = 4 / 9,
    out_pos_y: float = 3 / 9,
):
    img_y, img_x, _ = orig_img.shape
    out_img_x, out_img_y = out_size
    out_img_shape = (out_img_y, out_img_x, orig_img.shape[-1])

    # find the bounds of the object
    obj_xmin, obj_xmax, obj_ymin, obj_ymax = get_mask_bounds(orig_mask)

    # original face height
    obj_height = abs(obj_ymax - obj_ymin)
    obj_width = abs(obj_xmax - obj_xmin)

    # image resize ratio
    if obj_height > obj_width:
        re_ratio = (out_img_y / obj_height) * out_obj_scale
    else:
        re_ratio = (out_img_x / obj_width) * out_obj_scale

    # resized image size
    re_img_x = int(img_x * re_ratio)
    re_img_y = int(img_y * re_ratio)

    # resized image and mask
    re_img = cv2.resize(orig_img, (re_img_x, re_img_y))
    re_mask = cv2.resize(orig_mask, (re_img_x, re_img_y))

    # face center coords in original image
    face_center_x = (obj_xmax + obj_xmin) // 2
    face_center_y = (obj_ymax + obj_ymin) // 2

    # face center coords in resized image
    re_face_center_x = int(face_center_x * re_ratio)
    re_face_center_y = int(face_center_y * re_ratio)

    # crop of resized image
    re_crop_x1 = int(max(re_face_center_x - (out_img_x * out_pos_x), 0))
    re_crop_y1 = int(max(re_face_center_y - (out_img_y * out_pos_y), 0))

    re_crop_x2 = int(min(re_face_center_x + (out_img_x * (1 - out_pos_x)), re_img_x))
    re_crop_y2 = int(min(re_face_center_y + (out_img_y * (1 - out_pos_y)), re_img_y))

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


def get_mask_bounds(mask_cv2) -> (int, int, int, int):
    white_pixels = np.where(mask_cv2[:, :, 0] != 0)
    ymin = white_pixels[0].min()
    ymax = white_pixels[0].max()
    xmin = white_pixels[1].min()
    xmax = white_pixels[1].max()
    return xmin, xmax, ymin, ymax
