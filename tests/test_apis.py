import typing

import pytest
from fastapi.testclient import TestClient

from daras_ai_v2.base import (
    BasePage,
    get_example_request_body,
    get_or_create_doc,
    get_doc_ref,
)
from pages.ChyronPlant import ChyronPlantPage
from pages.CompareLM import CompareLMPage
from pages.CompareText2Img import CompareText2ImgPage
from pages.EmailFaceInpainting import EmailFaceInpaintingPage
from pages.FaceInpainting import FaceInpaintingPage
from pages.GoogleImageGen import GoogleImageGenPage
from pages.ImageSegmentation import ImageSegmentationPage
from pages.Img2Img import Img2ImgPage
from pages.LetterWriter import LetterWriterPage
from pages.Lipsync import LipsyncPage
from pages.LipsyncTTS import LipsyncTTSPage
from pages.ObjectInpainting import ObjectInpaintingPage
from pages.SEOSummary import SEOSummaryPage
from pages.SocialLookupEmail import SocialLookupEmailPage
from pages.TextToSpeech import TextToSpeechPage
from server import app

client = TestClient(app)

pages_to_test = [
    ChyronPlantPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    LetterWriterPage,
    LipsyncPage,
    CompareLMPage,
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
]


@pytest.mark.parametrize("page_cls", pages_to_test)
def test_apis_basic(page_cls: typing.Type[BasePage]):
    page = page_cls()
    state = get_or_create_doc(get_doc_ref(page.doc_name)).to_dict()

    r = client.post(
        page.endpoint,
        json=get_example_request_body(page.RequestModel, state),
    )

    assert r.ok, r.content
