import typing

import requests
from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai.image_input import (
    upload_file_from_bytes,
    resize_img_scale,
)
from daras_ai_v2.base import BasePage, gooey_rng
from daras_ai_v2.img_model_settings_widgets import (
    img_model_settings,
    model_selector,
)
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.serp_search import call_serp_api
from daras_ai_v2.serp_search_locations import (
    serp_search_location_selectbox,
    GoogleSearchLocationMixin,
    SerpSearchType,
    SerpSearchLocation,
)
from daras_ai_v2.stable_diffusion import (
    img2img,
    Img2ImgModels,
    SD_IMG_MAX_SIZE,
    instruct_pix2pix,
)


class GoogleImageGenPage(BasePage):
    title = "Render Image Search Results with AI"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/eb23c078-88da-11ee-aa86-02420a000165/web%20search%20render.png.png"
    workflow = Workflow.GOOGLE_IMAGE_GEN
    slug_versions = ["GoogleImageGen", "render-images-with-ai"]

    sane_defaults = dict(
        num_outputs=1,
        quality=50,
        guidance_scale=7.5,
        prompt_strength=0.5,
        sd_2_upscaling=False,
        seed=42,
        image_guidance_scale=1.2,
        serp_search_type=SerpSearchType.SEARCH,
        serp_search_location=SerpSearchLocation.UNITED_STATES,
    )

    class RequestModel(GoogleSearchLocationMixin, BasePage.RequestModel):
        search_query: str
        text_prompt: str

        selected_model: typing.Literal[tuple(e.name for e in Img2ImgModels)] | None = (
            None
        )

        negative_prompt: str | None = None

        num_outputs: int | None = None
        quality: int | None = None

        guidance_scale: float | None = None
        prompt_strength: float | None = None

        sd_2_upscaling: bool | None = None

        seed: int | None = None

        image_guidance_scale: float | None = None

    class ResponseModel(BaseModel):
        output_images: list[str]

        image_urls: list[str]
        selected_image: str | None = None

    def related_workflows(self):
        from recipes.ObjectInpainting import ObjectInpaintingPage
        from recipes.QRCodeGenerator import QRCodeGeneratorPage
        from recipes.SEOSummary import SEOSummaryPage
        from recipes.CompareText2Img import CompareText2ImgPage

        return [
            ObjectInpaintingPage,
            QRCodeGeneratorPage,
            SEOSummaryPage,
            CompareText2ImgPage,
        ]

    def render_description(self):
        gui.write(
            """
        This workflow creates unique, relevant images to help your site rank well for a given search query.

How It Works:
1. Looks up the top-ranked image for your search query
2. Alters the image using your text prompt using Stable Diffusion or DallE

The result is a fantastic, one of kind image that's relevant to your search (and should rank well on Google).
        """
        )

    def run(self, state: dict):
        request: GoogleImageGenPage.RequestModel = self.RequestModel.model_validate(
            state
        )

        yield "Googling..."

        serp_results = call_serp_api(
            request.search_query,
            search_type=SerpSearchType.IMAGES,
            search_location=request.serp_search_location,
        )
        image_urls = [
            link
            for result in serp_results.get("images", [])
            if (link := result.get("imageUrl"))
        ][:10]
        gooey_rng.shuffle(image_urls)

        yield "Downloading..."

        state["image_urls"] = image_urls
        # If model is not selected, don't do anything else
        if not state["selected_model"]:
            state["output_images"] = image_urls
            return  # Break out of the generator

        selected_image_bytes = None
        for selected_image_url in image_urls:
            try:
                selected_image_bytes = requests.get(selected_image_url).content
                selected_image_bytes = resize_img_scale(
                    selected_image_bytes, SD_IMG_MAX_SIZE
                )
            except (IOError, ConnectionError, ValueError):
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

        if request.selected_model == Img2ImgModels.instruct_pix2pix.name:
            state["output_images"] = instruct_pix2pix(
                prompt=request.text_prompt,
                num_outputs=request.num_outputs,
                num_inference_steps=request.quality,
                negative_prompt=request.negative_prompt,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
                images=[selected_image_url],
                image_guidance_scale=request.image_guidance_scale,
            )
        else:
            state["output_images"] = yield from img2img(
                prompt=request.text_prompt,
                negative_prompt=request.negative_prompt,
                init_image=selected_image_url,
                init_image_bytes=selected_image_bytes,
                selected_model=request.selected_model,
                num_inference_steps=request.quality,
                prompt_strength=request.prompt_strength,
                num_outputs=request.num_outputs,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
            )

    def render_form_v2(self):
        gui.text_input(
            """
            #### 🔎 Google Image Search
            Type a query you'd use in [Google image search](https://images.google.com/?gws_rd=ssl)
            """,
            key="search_query",
        )
        model_selector(Img2ImgModels)
        gui.text_area(
            """
            #### 👩‍💻 Prompt
            Describe how you want to edit the photo in words
            """,
            key="text_prompt",
            disabled=gui.session_state.get("selected_model") is None,
        )

    def render_usage_guide(self):
        youtube_video("rnjvtaYYe8g")

    def render_settings(self):
        img_model_settings(Img2ImgModels, render_model_selector=False)
        serp_search_location_selectbox()

    def render_output(self):
        out_imgs = gui.session_state.get("output_images")
        if out_imgs:
            for img in out_imgs:
                gui.image(
                    img, caption="#### Generated Image", show_download_button=True
                )
        else:
            gui.div()

    def render_steps(self):
        image_urls = gui.session_state.get("image_urls")
        if image_urls:
            gui.write("**Image URLs**")
            gui.json(image_urls, expanded=False)
        else:
            gui.div()

        selected_image = gui.session_state.get("selected_image")
        if selected_image:
            gui.image(selected_image, caption="Selected Image")
        else:
            gui.div()

    def render_run_preview_output(self, state: dict):
        gui.write(
            f"""
            **Google Search Query** `{state.get("search_query", "")}` \\
            **Prompt** `{state.get("text_prompt", "")}`
            """
        )

        out_imgs = state.get("output_images")
        if out_imgs:
            gui.image(out_imgs[0], caption="Generated Image")
