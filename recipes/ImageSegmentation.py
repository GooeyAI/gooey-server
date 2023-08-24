import typing
from pathlib import Path

import PIL
import numpy as np
import requests
import gooey_ui as st
from pydantic import BaseModel

from bots.models import Workflow
from daras_ai.image_input import (
    upload_file_from_bytes,
    cv2_img_to_bytes,
    bytes_to_cv2_img,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.image_segmentation import u2net, ImageSegmentationModels, dis
from daras_ai_v2.img_io import opencv_to_pil, pil_to_bytes
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.polygon_fitter import (
    appx_best_fit_ngon,
    best_fit_rotated_rect,
)
from daras_ai_v2.repositioning import (
    reposition_object,
    get_mask_bounds,
    repositioning_preview_widget,
)


class ImageSegmentationPage(BasePage):
    title = "AI Background Changer"
    workflow = Workflow.IMAGE_SEGMENTATION
    slug_versions = ["ImageSegmentation", "remove-image-background-with-ai"]

    sane_defaults = {
        "mask_threshold": 0.5,
        "rect_persepective_transform": False,
        "reflection_opacity": 0,
        "obj_scale": 0.8,
        "obj_pos_x": 0.5,
        "obj_pos_y": 0.5,
    }

    class RequestModel(BaseModel):
        input_image: str

        selected_model: typing.Literal[
            tuple(e.name for e in ImageSegmentationModels)
        ] | None
        mask_threshold: float | None

        rect_persepective_transform: bool | None
        reflection_opacity: float | None

        obj_scale: float | None
        obj_pos_x: float | None
        obj_pos_y: float | None

    class ResponseModel(BaseModel):
        output_image: str
        cutout_image: str
        resized_image: str
        resized_mask: str

    def related_workflows(self) -> list:
        from recipes.ObjectInpainting import ObjectInpaintingPage
        from recipes.Img2Img import Img2ImgPage
        from recipes.FaceInpainting import FaceInpaintingPage
        from recipes.CompareText2Img import CompareText2ImgPage

        return [
            ObjectInpaintingPage,
            Img2ImgPage,
            FaceInpaintingPage,
            CompareText2ImgPage,
        ]

    def render_form_v2(self):
        st.file_uploader(
            """
            ### Input Photo
            Give us a photo of anything
            """,
            key="input_image",
            upload_meta=dict(resize=f"{2048**2}@>"),
        )

    def validate_form_v2(self):
        input_image = st.session_state.get("input_image")
        assert input_image, "Please provide an Input Photo"

    def render_settings(self):
        enum_selector(
            ImageSegmentationModels,
            "#### Model",
            key="selected_model",
        )

        st.slider(
            """
            #### Edge Threshold
            Helps to remove edge artifacts. `0` will turn this off. `0.9` will aggressively cut down edges. 
            """,
            min_value=0.0,
            max_value=0.9,
            key="mask_threshold",
        )

        st.write(
            """
            #### Fix Skewed Perspective
            
            Automatically transform the perspective of the image to make objects look like a perfect rectangle  
            """
        )
        st.checkbox(
            "Fix Skewed Perspective",
            key="rect_persepective_transform",
        )

        st.write(
            """
            #### Add reflections
            """
        )
        col1, _ = st.columns(2)
        with col1:
            st.slider("Reflection Opacity", key="reflection_opacity")

        # st.write(
        #     """
        #     ##### Add Drop shadow
        #     """
        # )
        # col1, _ = st.columns(2)
        # with col1:
        #     st.slider("Shadow ", key="reflection_opacity")

        st.write(
            """
            #### Object Repositioning Settings
            """
        )

        st.write("How _big_ should the object look?")
        col1, _ = st.columns(2)
        with col1:
            obj_scale = st.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                key="obj_scale",
            )

        st.write("_Where_ would you like to place the object in the scene?")
        col1, col2 = st.columns(2)
        with col1:
            pos_x = st.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_x",
            )
        with col2:
            pos_y = st.slider(
                "Position Y",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_y",
            )

        import cv2

        # show an example image
        img_cv2 = cv2.imread("static/obj.png")
        mask_cv2 = cv2.imread("static/obj_mask.png")

        repositioning_preview_widget(
            img_cv2=img_cv2,
            mask_cv2=mask_cv2,
            obj_scale=obj_scale,
            pos_x=pos_x,
            pos_y=pos_y,
            out_size=(img_cv2.shape[1], img_cv2.shape[0]),
        )

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: ImageSegmentationPage.RequestModel = self.RequestModel.parse_obj(state)

        yield f"Running {ImageSegmentationModels[request.selected_model].value}..."

        match request.selected_model:
            case ImageSegmentationModels.u2net.name:
                mask_bytes = u2net(request.input_image)
            case _:
                mask_bytes = dis(request.input_image)

        img_bytes = requests.get(request.input_image).content

        yield "Thresholding..."

        img_cv2 = bytes_to_cv2_img(img_bytes)
        mask_cv2 = bytes_to_cv2_img(mask_bytes)

        threshold_value = int(255 * request.mask_threshold)
        mask_cv2[mask_cv2 < threshold_value] = 0

        import cv2

        kernel = np.ones((5, 5), np.float32) / 10
        mask_cv2 = cv2.filter2D(mask_cv2, -1, kernel)

        state["output_image"] = upload_file_from_bytes(
            f"gooey.ai Segmentation Mask - {Path(request.input_image).stem}.png",
            cv2_img_to_bytes(mask_cv2),
        )

        if request.rect_persepective_transform:
            yield "Fixing Perspective..."

            src_quad = np.float32(appx_best_fit_ngon(mask_cv2))
            dst_quad = best_fit_rotated_rect(mask_cv2)

            height, width, _ = img_cv2.shape

            matrix = cv2.getPerspectiveTransform(src_quad, dst_quad)
            img_cv2 = cv2.warpPerspective(img_cv2, matrix, (width, height))
            mask_cv2 = cv2.warpPerspective(mask_cv2, matrix, (width, height))

        yield "Repositioning..."

        img_cv2, mask_cv2 = reposition_object(
            orig_img=img_cv2,
            orig_mask=mask_cv2,
            out_size=(img_cv2.shape[1], img_cv2.shape[0]),
            out_obj_scale=request.obj_scale,
            out_pos_x=request.obj_pos_x,
            out_pos_y=request.obj_pos_y,
        )
        state["resized_image"] = upload_file_from_bytes(
            "re_image.png", cv2_img_to_bytes(img_cv2)
        )
        state["resized_mask"] = upload_file_from_bytes(
            "re_mask.png", cv2_img_to_bytes(mask_cv2)
        )

        bg_color = (255, 255, 255)
        # bg_color = (0, 0, 0)

        im_pil = opencv_to_pil(img_cv2)
        cutout_pil = PIL.Image.new("RGB", im_pil.size, bg_color)
        mask_pil = opencv_to_pil(mask_cv2).convert("L")
        cutout_pil.paste(im_pil, mask=mask_pil)

        if request.reflection_opacity:
            yield "Adding reflections..."

            y_padding = 10

            xmin, xmax, ymin, ymax = get_mask_bounds(mask_cv2)
            crop = (
                xmin,
                ymin,
                xmax,
                ymin + (cutout_pil.size[1] - ymax) - y_padding,
            )

            reflection_pil = PIL.ImageOps.flip(cutout_pil).crop(crop)
            reflection_mask_pil = PIL.ImageOps.flip(mask_pil).crop(crop).convert("1")

            background_pil = PIL.Image.new("RGB", reflection_pil.size, bg_color)
            gradient = generate_gradient_pil(
                *reflection_pil.size, request.reflection_opacity
            )
            reflection_pil = PIL.Image.composite(
                background_pil, reflection_pil, gradient
            )

            cutout_pil.paste(
                reflection_pil,
                (xmin, ymax + y_padding),
                mask=reflection_mask_pil,
            )

        state["cutout_image"] = upload_file_from_bytes(
            f"gooey.ai Cutout - {Path(request.input_image).stem}.png",
            pil_to_bytes(cutout_pil),
        )
        yield

    def render_output(self):
        self.render_example(st.session_state)

    def render_steps(self):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            input_image = st.session_state.get("input_image")
            if input_image:
                st.image(input_image, caption="Input Photo")
            else:
                st.div()

        with col2:
            output_image = st.session_state.get("output_image")
            if output_image:
                st.image(output_image, caption=f"Segmentation Mask")
            else:
                st.div()

        with col3:
            resized_image = st.session_state.get("resized_image")
            if resized_image:
                st.image(resized_image, caption=f"Resized Image")
            else:
                st.div()

            resized_mask = st.session_state.get("resized_mask")
            if resized_mask:
                st.image(resized_mask, caption=f"Resized Mask")
            else:
                st.div()

        with col4:
            cutout_image = st.session_state.get("cutout_image")
            if cutout_image:
                st.image(cutout_image, caption=f"Cutout Image")
            else:
                st.div()

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)

        with col1:
            input_image = state.get("input_image")
            if input_image:
                st.image(input_image, caption="Input Photo")
            else:
                st.div()

        with col2:
            cutout_image = state.get("cutout_image")
            if cutout_image:
                st.image(cutout_image, caption=f"Cutout Image")
            else:
                st.div()

    def preview_description(self, state: dict) -> str:
        return "Use Dichotomous Image Segmentation to remove unwanted backgrounds from your images and correct perspective. Awesome when used with other Gooey.AI steps."

    def render_usage_guide(self):
        youtube_video("hSsCMloAQ-8")


def _add_shadow(img_pil):
    draw = PIL.ImageDraw.Draw(img_pil)
    # draw.ellipse([(xmin, ymin), (xmax, ymin)], fill="#000")
    return img_pil


def generate_gradient_pil(width, height, opacity) -> PIL.Image:
    top = 100 - opacity
    btm = 100

    gtop = 255 * top // 100
    gbtm = 255 * btm // 100
    grady = np.linspace(gbtm, gtop, height, dtype=np.uint8)
    gradx = np.linspace(1, 1, width, dtype=np.uint8)
    grad = np.outer(grady, gradx)
    grad = np.flip(grad, axis=0)

    # alternate method
    # grad = np.linspace(0, 255, hh, dtype=np.uint8)
    # grad = np.linspace(gbtm, gtop, hh, dtype=np.uint8)
    # grad = np.tile(grad, (ww, 1))
    # grad = np.transpose(grad)
    # grad = np.flip(grad, axis=0)

    return PIL.Image.fromarray(grad, mode="L")


def _reflect(img_cv2, opacity):
    top = opacity
    btm = 0

    # add opaque alpha channel to input
    img_cv2 = cv2.cvtColor(img_cv2, cv2.COLOR_RGB2BGRA)

    hh, ww = img_cv2.shape[:2]

    # flip the input
    flip = np.flip(img_cv2, axis=0)

    hh //= 3
    flip = flip[:hh, :, :]

    # make vertical gradient that is bright at top and dark at bottom as alpha channel for the flipped image
    gtop = 255 * top // 100
    gbtm = 255 * btm // 100
    grady = np.linspace(gbtm, gtop, hh, dtype=np.uint8)
    gradx = np.linspace(1, 1, ww, dtype=np.uint8)
    grad = np.outer(grady, gradx)
    grad = np.flip(grad, axis=0)
    # # alternate method
    # grad = np.linspace(0, 255, hh, dtype=np.uint8)
    # grad = np.linspace(gbtm, gtop, hh, dtype=np.uint8)
    # grad = np.tile(grad, (ww, 1))
    # grad = np.transpose(grad)
    # grad = np.flip(grad, axis=0)

    # put the gradient into the alpha channel of the flipped image
    flip = cv2.cvtColor(flip, cv2.COLOR_BGR2BGRA)
    flip[:, :, 3] = grad

    # concatenate the original and the flipped versions
    result = np.vstack((img_cv2, flip))

    return result
