import streamlit as st

from daras_ai.extract_face import extract_face_cv2, extract_and_reposition_face_cv2
from daras_ai.image_input import (
    resize_img,
    cv2_img_to_png,
    bytes_to_cv2_img,
)


def main():
    file = st.file_uploader("Photo")
    reposition = st.checkbox("Reposition", value=True)

    face_scale = st.slider("face size", min_value=0.1, max_value=1.0, value=0.2)
    pos_x = st.slider("pos x", min_value=0.0, max_value=1.0, value=3 / 9)
    pos_y = st.slider("pos y", min_value=0.0, max_value=1.0, value=4 / 9)

    if not file:
        return

    img_bytes = file.getvalue()

    resized_img_bytes = resize_img(img_bytes, (512, 512))

    image_cv2 = bytes_to_cv2_img(resized_img_bytes)
    if reposition:
        image_cv2, face_mask_cv2 = extract_and_reposition_face_cv2(
            image_cv2, face_scale=face_scale, pos_x=pos_x, pos_y=pos_y
        )
    else:
        face_mask_cv2 = extract_face_cv2(image_cv2)
    face_mask_bytes = cv2_img_to_png(face_mask_cv2)

    st.image(img_bytes, width=200)
    st.image(cv2_img_to_png(image_cv2), width=200)
    st.image(face_mask_bytes, width=200)


if __name__ == "__main__":
    main()
