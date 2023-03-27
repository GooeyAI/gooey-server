import typing

import pytest
from fastapi.testclient import TestClient

from auth_backend import force_authentication
from daras_ai_v2 import db
from daras_ai_v2.GoogleGPT import GoogleGPTPage
from daras_ai_v2.base import (
    BasePage,
    get_example_request_body,
)
from recipes.ChyronPlant import ChyronPlantPage
from recipes.CompareLLM import CompareLLMPage
from recipes.CompareText2Img import CompareText2ImgPage
from recipes.CompareUpscaler import CompareUpscalerPage
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
from recipes.TextToSpeech import TextToSpeechPage
from recipes.VideoBots import VideoBotsPage
from server import app

client = TestClient(app)

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
    SEOSummaryPage,
    GoogleImageGenPage,
    VideoBotsPage,
    CompareUpscalerPage,
    GoogleGPTPage,
    DocSearchPage,
    DocSummaryPage,
]


@pytest.mark.parametrize("page_cls", pages_to_test)
def test_apis_basic(page_cls: typing.Type[BasePage], test_auth_user):
    page = page_cls()
    state = db.get_or_create_doc(db.get_doc_ref(page.doc_name)).to_dict()

    with force_authentication(test_auth_user):
        r = client.post(
            page.endpoint,
            json=get_example_request_body(page.RequestModel, state),
            headers={"Authorization": f"Token None"},
        )

    print(r.content)
    assert r.ok
