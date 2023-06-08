import streamlit

import gooey_ui as gui
from daras_ai_v2.GoogleGPT import GoogleGPTPage
from daras_ai_v2.face_restoration import map_parallel
from daras_ai_v2.grid_layout_widget import grid_layout
from recipes.CompareLLM import CompareLLMPage
from recipes.CompareText2Img import CompareText2ImgPage
from recipes.CompareUpscaler import CompareUpscalerPage
from recipes.DeforumSD import DeforumSDPage
from recipes.DocSearch import DocSearchPage
from recipes.DocSummary import DocSummaryPage
from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
from recipes.FaceInpainting import FaceInpaintingPage
from recipes.GoogleImageGen import GoogleImageGenPage
from recipes.ImageSegmentation import ImageSegmentationPage
from recipes.Img2Img import Img2ImgPage
from recipes.Lipsync import LipsyncPage
from recipes.LipsyncTTS import LipsyncTTSPage
from recipes.ObjectInpainting import ObjectInpaintingPage
from recipes.SEOSummary import SEOSummaryPage
from recipes.SocialLookupEmail import SocialLookupEmailPage
from recipes.Text2Audio import Text2AudioPage
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import VideoBotsPage
from recipes.asr import AsrPage


def render():
    page_classes = [
        DocSearchPage,
        DocSummaryPage,
        GoogleGPTPage,
        VideoBotsPage,
        LipsyncTTSPage,
        TextToSpeechPage,
        AsrPage,
        LipsyncPage,
        DeforumSDPage,
        CompareText2ImgPage,
        Text2AudioPage,
        Img2ImgPage,
        FaceInpaintingPage,
        GoogleImageGenPage,
        CompareUpscalerPage,
        SEOSummaryPage,
        EmailFaceInpaintingPage,
        SocialLookupEmailPage,
        ObjectInpaintingPage,
        ImageSegmentationPage,
        CompareLLMPage,
        # ChyronPlantPage,
    ]
    pages = [page_cls() for page_cls in page_classes]
    with gui.spinner():
        all_examples = map_parallel(lambda page: page.get_recipe_doc().to_dict(), pages)

    def _render(args):
        page, example_doc = args

        gui.markdown(
            # language=html
            f"""
<a style="font-size: 24px" href="{page.app_url()}" target = "_top">
    <h2>{page.title}</h2>
</a>
            """,
            unsafe_allow_html=True,
        )

        preview = page.preview_description(example_doc)
        if preview:
            gui.write(preview)
        else:
            page.render_description()

        page.render_example(example_doc)

    grid_layout(3, zip(pages, all_examples), _render)
