import typing

import pytest
from fastapi.testclient import TestClient

from daras_ai_v2 import db
from daras_ai_v2.base import (
    BasePage,
    get_example_request_body,
)
from daras_ai_v2.settings import API_SECRET_KEY
from recipes.ChyronPlant import ChyronPlantPage
from recipes.CompareLM import CompareLMPage
from recipes.CompareText2Img import CompareText2ImgPage
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
from recipes.TextToSpeech import TextToSpeechPage
from server import app

client = TestClient(app)

pages_to_test = [
    ChyronPlantPage,
    FaceInpaintingPage,
    EmailFaceInpaintingPage,
    LetterWriterPage,
    LipsyncPage,
    # CompareLMPage,
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
    state = db.get_or_create_doc(db.get_doc_ref(page.doc_name)).to_dict()

    r = client.post(
        page.endpoint,
        json=get_example_request_body(page.RequestModel, state),
        headers={"Authorization": f"Token {API_SECRET_KEY}"},
    )

    assert r.ok, r.content
