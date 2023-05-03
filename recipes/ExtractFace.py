import cv2
import streamlit2 as st

from daras_ai.extract_face import extract_face_cv2, extract_and_reposition_face_cv2
from daras_ai.image_input import (
    cv2_img_to_bytes,
    bytes_to_cv2_img,
    resize_img_scale,
)
from daras_ai_v2.extract_face import rgb_mask_to_rgba


def main():
    st.write("### A simple app to extract faces from images")

    file = st.file_uploader("Photo")
    reposition = st.checkbox("Reposition", value=True)

    face_scale = st.slider("face size", min_value=0.1, max_value=1.0, value=0.2)
    pos_x = st.slider("pos x", min_value=0.0, max_value=1.0, value=3 / 9)
    pos_y = st.slider("pos y", min_value=0.0, max_value=1.0, value=4 / 9)

    if not file:
        return

    img_bytes = file.getvalue()

    resized_img_bytes = resize_img_scale(img_bytes, (1024, 1024))

    image_cv2 = bytes_to_cv2_img(resized_img_bytes)
    if reposition:
        image_cv2, face_mask_cv2 = extract_and_reposition_face_cv2(
            image_cv2, out_face_scale=face_scale, out_pos_x=pos_x, out_pos_y=pos_y
        )
    else:
        face_mask_cv2 = extract_face_cv2(image_cv2)
    face_mask_cv2 = cv2.GaussianBlur(face_mask_cv2, (0, 0), 5)
    face_mask_bytes = cv2_img_to_bytes(face_mask_cv2)

    st.image(img_bytes, width=200)
    st.image(cv2_img_to_bytes(image_cv2), width=200)
    st.image(face_mask_bytes, width=200)

    st.image(rgb_mask_to_rgba(face_mask_bytes), width=200)


if __name__ == "__main__":
    main()
