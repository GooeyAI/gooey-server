import io

import PIL


def opencv_to_pil(img_cv2, mode="RGB") -> PIL.Image:
    import cv2

    img_cv2 = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
    return PIL.Image.fromarray(img_cv2, mode=mode)


def pil_to_bytes(img_pil: PIL.Image) -> bytes:
    img_byte_arr = io.BytesIO()
    img_pil.save(img_byte_arr, format="PNG")
    return img_byte_arr.getvalue()
