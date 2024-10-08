import pytest

from daras_ai_v2.vector_search import is_yt_dlp_able_url


@pytest.mark.parametrize(
    "url, expected",
    [
        # youtube video links
        ("https://www.youtube.com/watch?v=vtB1J_zCv8I", True),
        ("https://youtu.be/vtB1J_zCv8I?si=UUGHp_zxzg8YT4sW", True),
        # facebook video links
        ("https://www.facebook.com/watch/?v=724258088377627", True),
        ("https://fb.watch/uMRczAWxcU/", True),
        ("https://www.facebook.com/unheardkashmir/videos/724258088377627", True),
        ("https://www.facebook.com/share/v/qmq7SvGX4Y5smixX/", True),
        # other fb links
        ("https://www.facebook.com/GooeyAI", False),
        ("https://www.facebook.com/share/p/KtodMirKmiGqhyfZ/", False),
        ("https://www.facebook.com/marketplace/item/7206063666166896/", False),
    ],
)
def test_is_yt_dlp_able_url(url, expected):
    assert is_yt_dlp_able_url(url) == expected
