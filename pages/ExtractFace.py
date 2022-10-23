import streamlit as st

from daras_ai.extract_face import extract_face_cv2, extract_and_reposition_face_cv2
from daras_ai.image_input import resize_img, cv2_img_to_png, bytes_to_cv2_img


def main():
    file = st.file_uploader("Photo")
    reposition = st.checkbox("Reposition", value=True)

    if not file:
        return

    img_bytes = file.getvalue()

    resized_img_bytes = resize_img(img_bytes, (512, 512))

    image_cv2 = bytes_to_cv2_img(resized_img_bytes)
    if reposition:
        image_cv2, face_mask_cv2 = extract_and_reposition_face_cv2(image_cv2)
    else:
        face_mask_cv2 = extract_face_cv2(image_cv2)
    face_mask_bytes = cv2_img_to_png(face_mask_cv2)

    st.image(image_cv2, width=200)
    st.image(face_mask_bytes, width=200)


if __name__ == "__main__":
    main()
