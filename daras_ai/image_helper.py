import cv2
import requests
from daras_ai.image_input import (
    upload_file_from_bytes,
    cv2_img_to_png,
    bytes_to_cv2_img,
)


def add_watermark_to_images(self, output_images):
    output_images_with_watermark = []
    url_logo = "https://static.wixstatic.com/media/07c536_57cbebd88cab4899b914a739df226e7e~mv2.png/v1/fill/w_276,h_91,al_c,q_85,usm_0.66_1.00_0.01,enc_auto/Screenshot%202022-09-27%20at%2010_57_07%20PM.png"
    for url in output_images:
        img_bytes = requests.get(url).content
        logo_bytes = requests.get(url_logo).content
        img = bytes_to_cv2_img(img_bytes)
        logo = bytes_to_cv2_img(logo_bytes)
        # height and width of the logo
        h_logo, w_logo, _ = logo.shape

        # height and width of the image
        h_img, w_img, _ = img.shape
        # place our watermark
        center_y = int(h_img)
        center_x = int(w_img)
        # calculating from top, bottom, right and left
        top_y = center_y - int(h_logo)
        left_x = center_x - int(w_logo)
        bottom_y = top_y + h_logo
        right_x = left_x + w_logo
        # adding watermark to the image
        destination = img[top_y:bottom_y, left_x:right_x]
        result = cv2.addWeighted(destination, 1, logo, 0.4, 0)
        img[top_y:bottom_y, left_x:right_x] = result
        updated_url = upload_file_from_bytes("out.png", cv2_img_to_png(img))
        output_images_with_watermark.append(updated_url)
    return output_images_with_watermark
