from daras_ai_v2.GoogleGPT import GoogleGPTPage
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
from recipes.asr import AsrPage

all_home_pages = [
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

all_api_pages = [
    ChyronPlantPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    LetterWriterPage,
    LipsyncPage,
    CompareLLMPage,
    ImageSegmentationPage,
    TextToSpeechPage,
    LipsyncTTSPage,
    DeforumSDPage,
    Img2ImgPage,
    ObjectInpaintingPage,
    SocialLookupEmailPage,
    CompareText2ImgPage,
    Text2AudioPage,
    SEOSummaryPage,
    GoogleImageGenPage,
    VideoBotsPage,
    CompareUpscalerPage,
    GoogleGPTPage,
    DocSearchPage,
    DocSummaryPage,
    AsrPage,
]

pages_to_test = [
    ChyronPlantPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    # LetterWriterPage, ## deprecated
    LipsyncPage,
    CompareLLMPage,
    ImageSegmentationPage,
    TextToSpeechPage,
    LipsyncTTSPage,
    # DeforumSDPage, ## too slow!
    Img2ImgPage,
    ObjectInpaintingPage,
    SocialLookupEmailPage,
    CompareText2ImgPage,
    Text2AudioPage,
    SEOSummaryPage,
    GoogleImageGenPage,
    VideoBotsPage,
    CompareUpscalerPage,
    GoogleGPTPage,
    DocSearchPage,
    DocSummaryPage,
    AsrPage,
]
