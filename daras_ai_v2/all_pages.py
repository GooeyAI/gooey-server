import typing

from django.db import models

from daras_ai_v2.GoogleGPT import GoogleGPTPage
from daras_ai_v2.base import BasePage
from recipes.RelatedQnA import RelatedQnAPage
from recipes.RelatedQnADoc import RelatedQnADocPage
from recipes.SmartGPT import SmartGPTPage
from recipes.ChyronPlant import ChyronPlantPage
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
from recipes.LetterWriter import LetterWriterPage
from recipes.Lipsync import LipsyncPage
from recipes.LipsyncTTS import LipsyncTTSPage
from recipes.ObjectInpainting import ObjectInpaintingPage
from recipes.SEOSummary import SEOSummaryPage
from recipes.SocialLookupEmail import SocialLookupEmailPage
from recipes.Text2Audio import Text2AudioPage
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import VideoBotsPage
from recipes.DocExtract import DocExtractPage
from recipes.asr import AsrPage
from recipes.QRCodeGenerator import QRCodeGeneratorPage
from recipes.embeddings_page import EmbeddingsPage
from recipes.Translate import TranslationPage

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
    TranslationPage,
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


class Workflow(models.IntegerChoices):
    DOCSEARCH = (1, DocSearchPage.__name__)
    DOCSUMMARY = (2, DocSummaryPage.__name__)
    GOOGLEGPT = (3, GoogleGPTPage.__name__)
    VIDEOBOTS = (4, VideoBotsPage.__name__)
    LIPSYNCTTS = (5, LipsyncTTSPage.__name__)
    TEXTTOSPEECH = (6, TextToSpeechPage.__name__)
    ASR = (7, AsrPage.__name__)
    LIPSYNC = (8, LipsyncPage.__name__)
    DEFORUMSD = (9, DeforumSDPage.__name__)
    COMPARETEXT2IMG = (10, CompareText2ImgPage.__name__)
    TEXT2AUDIO = (11, Text2AudioPage.__name__)
    IMG2IMG = (12, Img2ImgPage.__name__)
    FACEINPAINTING = (13, FaceInpaintingPage.__name__)
    GOOGLEIMAGEGEN = (14, GoogleImageGenPage.__name__)
    COMPAREUPSCALER = (15, CompareUpscalerPage.__name__)
    SEOSUMMARY = (16, SEOSummaryPage.__name__)
    EMAILFACEINPAINTING = (17, EmailFaceInpaintingPage.__name__)
    SOCIALLOOKUPEMAIL = (18, SocialLookupEmailPage.__name__)
    OBJECTINPAINTING = (19, ObjectInpaintingPage.__name__)
    IMAGESEGMENTATION = (20, ImageSegmentationPage.__name__)
    COMPARELLM = (21, CompareLLMPage.__name__)
    CHYRONPLANT = (22, ChyronPlantPage.__name__)
    LETTERWRITER = (23, LetterWriterPage.__name__)
    SMARTGPT = (24, SmartGPTPage.__name__)
    QRCODE = (25, QRCodeGeneratorPage.__name__)
    YOUTUBEBOT = (26, DocExtractPage.__name__)
    TRANSLATE = (27, TranslationPage.__name__)

    @property
    def page_cls(self) -> typing.Type[BasePage]:
        return globals()[self.label]
