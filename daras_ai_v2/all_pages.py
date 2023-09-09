import re
import typing

from bots.models import Workflow
from daras_ai_v2.base import BasePage
from recipes.ChyronPlant import ChyronPlantPage
from recipes.CompareLLM import CompareLLMPage
from recipes.CompareText2Img import CompareText2ImgPage
from recipes.CompareUpscaler import CompareUpscalerPage
from recipes.DeforumSD import DeforumSDPage
from recipes.DocExtract import DocExtractPage
from recipes.DocSearch import DocSearchPage
from recipes.DocSummary import DocSummaryPage
from recipes.EmailFaceInpainting import EmailFaceInpaintingPage
from recipes.FaceInpainting import FaceInpaintingPage
from recipes.GoogleGPT import GoogleGPTPage
from recipes.GoogleImageGen import GoogleImageGenPage
from recipes.ImageSegmentation import ImageSegmentationPage
from recipes.Img2Img import Img2ImgPage
from recipes.LetterWriter import LetterWriterPage
from recipes.Lipsync import LipsyncPage
from recipes.LipsyncTTS import LipsyncTTSPage
from recipes.ObjectInpainting import ObjectInpaintingPage
from recipes.QRCodeGenerator import QRCodeGeneratorPage
from recipes.RelatedQnA import RelatedQnAPage
from recipes.RelatedQnADoc import RelatedQnADocPage
from recipes.SEOSummary import SEOSummaryPage
from recipes.SmartGPT import SmartGPTPage
from recipes.SocialLookupEmail import SocialLookupEmailPage
from recipes.Text2Audio import Text2AudioPage
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import VideoBotsPage
from recipes.asr import AsrPage
from recipes.embeddings_page import EmbeddingsPage

# note: the ordering here matters!
all_home_pages = [
    # top ones
    VideoBotsPage,
    DeforumSDPage,
    QRCodeGeneratorPage,
    # SEO tools
    GoogleGPTPage,
    SEOSummaryPage,
    RelatedQnAPage,
    # Image Tools
    ObjectInpaintingPage,
    CompareText2ImgPage,
    Img2ImgPage,
    # More Image
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    GoogleImageGenPage,
    # LipSync fun
    TextToSpeechPage,
    LipsyncPage,
    LipsyncTTSPage,
    # Text
    CompareLLMPage,
    DocSearchPage,
    SmartGPTPage,
    # Speech & Music
    AsrPage,
    # VideoPlayList,
    Text2AudioPage,
    # Other
    DocSummaryPage,
    RelatedQnADocPage,
    SocialLookupEmailPage,
    # More
    ImageSegmentationPage,
    CompareUpscalerPage,
    DocExtractPage,
]

# exposed as API
all_api_pages = all_home_pages.copy() + [
    ChyronPlantPage,
    LetterWriterPage,
    EmbeddingsPage,
]

# pytest suite
all_test_pages = all_api_pages.copy()
# deprecated
all_test_pages.remove(LetterWriterPage)


def normalize_slug(page_slug):
    return re.sub(r"[-_]", "", page_slug.lower())


page_slug_map: dict[str, typing.Type[BasePage]] = {
    normalize_slug(slug): page for page in all_api_pages for slug in page.slug_versions
}

workflow_map: dict[Workflow, typing.Type[BasePage]] = {
    page.workflow: page for page in all_api_pages
}
