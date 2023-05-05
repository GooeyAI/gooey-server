import gooey_ui as st


def main():
    from daras_ai.init import init_scripts
    from daras_ai_v2.GoogleGPT import GoogleGPTPage
    from recipes.DocSearch import DocSearchPage
    from recipes.DocSummary import DocSummaryPage
    from recipes.Lipsync import LipsyncPage
    from recipes.Text2Audio import Text2AudioPage
    from recipes.asr import AsrPage

    init_scripts()
    from daras_ai_v2.grid_layout_widget import grid_layout
    from recipes.CompareLLM import CompareLLMPage
    from recipes.CompareUpscaler import CompareUpscalerPage
    from recipes.VideoBots import VideoBotsPage
    from server import normalize_slug, page_map

    # try to load page from query params
    #
    query_params = st.get_query_params()
    try:
        page_slug = normalize_slug(query_params["page_slug"])
    except KeyError:
        pass
    else:
        # no page_slug provided - render explore page
        try:
            page = page_map[page_slug]
        except KeyError:
            st.error(f"## 404 - Page {page_slug!r} Not found")
        else:
            page().render()
        st.stop()
    from daras_ai_v2 import settings
    from daras_ai_v2.face_restoration import map_parallel
    from recipes.CompareText2Img import CompareText2ImgPage
    from recipes.DeforumSD import DeforumSDPage
    from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
    from recipes.FaceInpainting import FaceInpaintingPage
    from recipes.GoogleImageGen import GoogleImageGenPage
    from recipes.ImageSegmentation import ImageSegmentationPage
    from recipes.Img2Img import Img2ImgPage
    from recipes.LipsyncTTS import LipsyncTTSPage
    from recipes.ObjectInpainting import ObjectInpaintingPage
    from recipes.SEOSummary import SEOSummaryPage
    from recipes.SocialLookupEmail import SocialLookupEmailPage
    from recipes.TextToSpeech import TextToSpeechPage

    assert settings.GOOGLE_APPLICATION_CREDENTIALS
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
    with st.spinner():
        all_examples = map_parallel(lambda page: page.get_recipe_doc().to_dict(), pages)

    def _render(args):
        page, example_doc = args

        st.markdown(
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
            st.write(preview)
        else:
            page.render_description()

        page.render_example(example_doc)

    grid_layout(3, zip(pages, all_examples), _render)
