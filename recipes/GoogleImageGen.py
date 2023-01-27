import typing

import requests
import streamlit as st
from pydantic import BaseModel
from recipes import (
    SEOSummary,
    ObjectInpainting,
    ImageSegmentation,
    CompareText2Img,
)

from daras_ai.image_input import (
    upload_file_from_bytes,
    resize_img_contain,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.google_search import call_scaleserp
from daras_ai_v2.img_model_settings_widgets import (
    img_model_settings,
)
from daras_ai_v2.stable_diffusion import img2img, Img2ImgModels, SD_MAX_SIZE
from daras_ai_v2.utils import random


class GoogleImageGenPage(BasePage):
    title = "Render Image Search Results with AI"
    slug_versions = ["GoogleImageGen", "render-images-with-ai"]

    sane_defaults = {
        "num_outputs": 1,
        "quality": 50,
        "guidance_scale": 7.5,
        "prompt_strength": 0.5,
        "sd_2_upscaling": False,
        "seed": 42,
    }

    class RequestModel(BaseModel):
        search_query: str
        text_prompt: str

        selected_model: typing.Literal[tuple(e.name for e in Img2ImgModels)] | None

        negative_prompt: str | None

        num_outputs: int | None
        quality: int | None

        guidance_scale: float | None
        prompt_strength: float | None

        sd_2_upscaling: bool | None

        seed: int | None

    class ResponseModel(BaseModel):
        output_images: list[str]

        image_urls: list[str]
        selected_image: str

    def related_workflows(self):
        return [
            ObjectInpainting.ObjectInpaintingPage,
            ImageSegmentation.ImageSegmentationPage,
            SEOSummary.SEOSummaryPage,
            CompareText2Img.CompareText2ImgPage,
        ]

    def render_description(self):
        st.write(
            """
        This workflow creates unique, relevant images to help your site rank well for a given search query.

How It Works:
1. Looks up the top-ranked image for your search query
2. Alters the image using your text prompt using Stable Diffusion or DallE

The result is a fantastic, one of kind image that's relevant to your search (and should rank well on Google).
        """
        )

    def run(self, state: dict):
        request: GoogleImageGenPage.RequestModel = self.RequestModel.parse_obj(state)

        yield "Googling..."

        scaleserp_results = call_scaleserp(
            request.search_query,
            search_type="images",
            include_fields="image_results",
            images_size="medium",
        )
        image_urls = [
            result["image"]
            for result in scaleserp_results["image_results"]
            if "image" in result
        ][:10]
        random.shuffle(image_urls)

        state["image_urls"] = image_urls

        yield "Downloading..."

        selected_image_bytes = None
        for selected_image_url in image_urls:
            print(selected_image_url)
            selected_image_bytes = requests.get(selected_image_url).content
            try:
                selected_image_bytes = resize_img_contain(
                    selected_image_bytes, SD_MAX_SIZE
                )
            except ValueError:
                continue
            else:
                break
        if not selected_image_bytes:
            raise ValueError("Could not find an image! Please try another query?")

        selected_image_url = upload_file_from_bytes(
            "selected_img.png", selected_image_bytes
        )

        state["selected_image"] = selected_image_url

        yield "Generating Images..."

        state["output_images"] = img2img(
            prompt=request.text_prompt,
            negative_prompt=request.negative_prompt,
            init_image=selected_image_url,
            init_image_bytes=selected_image_bytes,
            ##
            selected_model=request.selected_model,
            num_inference_steps=request.quality,
            prompt_strength=request.prompt_strength,
            num_outputs=request.num_outputs,
            guidance_scale=request.guidance_scale,
            sd_2_upscaling=request.sd_2_upscaling,
            seed=request.seed,
        )

    def render_form_v2(self):
        st.text_input(
            """
            ### 🔎 Google Image Search
            Type a query you'd use in [Google image search](https://images.google.com/?gws_rd=ssl)
            """,
            key="search_query",
        )
        st.text_area(
            """
            ### 👩‍💻 Prompt
            Describe how you want to edit the photo in words
            """,
            key="text_prompt",
        )

    def render_settings(self):
        img_model_settings(Img2ImgModels)

    def render_output(self):
        out_imgs = st.session_state.get("output_images")
        if out_imgs:
            for img in out_imgs:
                st.image(img, caption="Generated Image")
        else:
            st.empty()

    def render_steps(self):
        image_urls = st.session_state.get("image_urls")
        if image_urls:
            st.write("**Image URLs**")
            st.json(image_urls, expanded=False)
        else:
            st.empty()

        selected_image = st.session_state.get("selected_image")
        if selected_image:
            st.image(selected_image, caption="Selected Image")
        else:
            st.empty()

    def render_example(self, state: dict):
        st.write(
            f"""
            **Google Search Query** `{state.get("search_query", '')}` \\
            **Prompt** `{state.get("text_prompt", '')}`
            """
        )

        out_imgs = state.get("output_images")
        if out_imgs:
            st.image(out_imgs[0], caption="Generated Image")

    def preview_description(self, state: dict) -> str:
        return "Enter a Google Image Search query + your Img2Img text prompt describing how to alter the result to create a unique, relevant ai generated images for any search query."


if __name__ == "__main__":
    GoogleImageGenPage().render()
