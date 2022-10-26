from daras_ai.extract_face import extract_face_cv2, extract_and_reposition_face_cv2
from daras_ai.image_input import bytes_to_cv2_img, cv2_img_to_bytes


def extract_face_img_bytes(img_bytes: bytes) -> (bytes, bytes):
    image_cv2 = bytes_to_cv2_img(img_bytes)
    image_cv2, face_mask_cv2 = extract_and_reposition_face_cv2(image_cv2)
    image_bytes = cv2_img_to_bytes(image_cv2)
    face_mask_bytes = cv2_img_to_bytes(face_mask_cv2)
    return image_bytes, face_mask_bytes
