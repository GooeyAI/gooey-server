from daras_ai.extract_face import extract_face_cv2, extract_and_reposition_face_cv2
from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes


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
    image_bytes = cv2_img_to_bytes(image_cv2)
    face_mask_bytes = cv2_img_to_bytes(face_mask_cv2)
    return image_bytes, face_mask_bytes
