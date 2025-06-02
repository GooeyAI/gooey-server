import typing
from pathlib import Path

import PIL
import numpy as np
from daras_ai_v2.pydantic_validation import FieldHttpUrl
import requests
import gooey_gui as gui
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
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/06fc595e-88db-11ee-b428-02420a000168/AI%20Background%20Remover.png.png"
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

    class RequestModel(BasePage.RequestModel):
        input_image: FieldHttpUrl

        selected_model: (
            typing.Literal[tuple(e.name for e in ImageSegmentationModels)] | None
        ) = None
        mask_threshold: float | None = None

        rect_persepective_transform: bool | None = None
        reflection_opacity: float | None = None

        obj_scale: float | None = None
        obj_pos_x: float | None = None
        obj_pos_y: float | None = None

    class ResponseModel(BaseModel):
        output_image: FieldHttpUrl
        cutout_image: FieldHttpUrl
        resized_image: FieldHttpUrl
        resized_mask: FieldHttpUrl

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
        gui.file_uploader(
            """
            #### Input Photo
            Give us a photo of anything
            """,
            key="input_image",
            upload_meta=dict(resize=f"{2048**2}@>"),
        )

    def validate_form_v2(self):
        input_image = gui.session_state.get("input_image")
        assert input_image, "Please provide an Input Photo"

    def render_settings(self):
        enum_selector(
            ImageSegmentationModels,
            "#### Model",
            key="selected_model",
        )

        gui.slider(
            """
            #### Edge Threshold
            Helps to remove edge artifacts. `0` will turn this off. `0.9` will aggressively cut down edges. 
            """,
            min_value=0.0,
            max_value=0.9,
            key="mask_threshold",
        )

        gui.write(
            """
            #### Fix Skewed Perspective
            
            Automatically transform the perspective of the image to make objects look like a perfect rectangle  
            """
        )
        gui.checkbox(
            "Fix Skewed Perspective",
            key="rect_persepective_transform",
        )

        gui.write(
            """
            #### Add reflections
            """
        )
        col1, _ = gui.columns(2)
        with col1:
            gui.slider("Reflection Opacity", key="reflection_opacity")

        # gui.write(
        #     """
        #     ##### Add Drop shadow
        #     """
        # )
        # col1, _ = gui.columns(2)
        # with col1:
        #     gui.slider("Shadow ", key="reflection_opacity")

        gui.write(
            """
            #### Object Repositioning Settings
            """
        )

        gui.write("How _big_ should the object look?")
        col1, _ = gui.columns(2)
        with col1:
            obj_scale = gui.slider(
                "Scale",
                min_value=0.1,
                max_value=1.0,
                key="obj_scale",
            )

        gui.write("_Where_ would you like to place the object in the scene?")
        col1, col2 = gui.columns(2)
        with col1:
            pos_x = gui.slider(
                "Position X",
                min_value=0.0,
                max_value=1.0,
                key="obj_pos_x",
            )
        with col2:
            pos_y = gui.slider(
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
        request: ImageSegmentationPage.RequestModel = self.RequestModel.model_validate(state)

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
        self.render_run_preview_output(gui.session_state)

    def render_steps(self):
        col1, col2, col3, col4 = gui.columns(4)

        with col1:
            input_image = gui.session_state.get("input_image")
            if input_image:
                gui.image(input_image, caption="Input Photo")
            else:
                gui.div()

        with col2:
            output_image = gui.session_state.get("output_image")
            if output_image:
                gui.image(output_image, caption="Segmentation Mask")
            else:
                gui.div()

        with col3:
            resized_image = gui.session_state.get("resized_image")
            if resized_image:
                gui.image(resized_image, caption="Resized Image")
            else:
                gui.div()

            resized_mask = gui.session_state.get("resized_mask")
            if resized_mask:
                gui.image(resized_mask, caption="Resized Mask")
            else:
                gui.div()

        with col4:
            cutout_image = gui.session_state.get("cutout_image")
            if cutout_image:
                gui.image(cutout_image, caption="Cutout Image")
            else:
                gui.div()

    def render_run_preview_output(self, state: dict):
        col1, col2 = gui.columns(2)

        with col1:
            input_image = state.get("input_image")
            if input_image:
                gui.image(input_image, caption="Input Photo", show_download_button=True)
            else:
                gui.div()

        with col2:
            cutout_image = state.get("cutout_image")
            if cutout_image:
                gui.image(cutout_image, caption="Cutout Image")
            else:
                gui.div()

    def render_usage_guide(self):
        youtube_video("hSsCMloAQ-8")


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
