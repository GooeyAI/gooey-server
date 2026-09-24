from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

import pytest

import gooey_gui as gui
from bots.sdg import SDG
from daras_ai_v2.base_v2 import DEFAULT_STATS_TITLE
from gooey_gui.core.renderer import NestingCtx, RenderTreeNode
from daras_ai_v2.loom_video_widget import youtube_embed_url
from daras_ai_v2.gooey_builder import (
    BUILDER_PROMPT_Q,
    _builder_prompts,
    builder_prompt_next_url,
)
from recipes.VideoBots_v2 import VideoBotsPageV2


def test_sdg_covers_all_seventeen_goals():
    assert [g.value for g in SDG] == list(range(1, 18))
    assert SDG(1).label == "No Poverty"
    assert SDG(17).label == "Partnerships for the Goals"


def test_sdg_urls_are_derived_from_the_number():
    """Zero-padded in the icon filename, bare in the goal url - the UN uses both."""
    assert SDG(1).icon_url.endswith("E_SDG_Icons-01.jpg")
    assert SDG(17).icon_url.endswith("E_SDG_Icons-17.jpg")
    assert SDG(1).un_url == "https://sdgs.un.org/goals/goal1"
    assert SDG(17).un_url == "https://sdgs.un.org/goals/goal17"


def make_pr(**kwargs):
    """A published run with every marketing field empty, overridden per test."""
    defaults = dict(
        photo_url="",
        banner_url="",
        video_url="",
        headline="",
        more_info_url="",
        more_info_text="",
        sdgs=[],
        stats_title="",
    )
    return SimpleNamespace(**(defaults | kwargs))


@pytest.mark.parametrize(
    "fields, expected_kind, expected_url",
    [
        (dict(video_url="v", banner_url="b", photo_url="p"), "video", "v"),
        (dict(banner_url="b", photo_url="p"), "banner", "b"),
        (dict(photo_url="p"), "photo", "p"),
    ],
)
def test_media_precedence(fields, expected_kind, expected_url):
    page = object.__new__(VideoBotsPageV2)
    page.workflow = 0
    media = page._about_media(make_pr(**fields))
    assert (media.kind, media.url) == (expected_kind, expected_url)


def test_a_youtube_video_url_becomes_an_iframe_embed():
    page = object.__new__(VideoBotsPageV2)
    page.workflow = 0
    media = page._about_media(
        make_pr(video_url="https://www.youtube.com/watch?v=a0cBLQndN8s&list=PLx")
    )
    assert (media.kind, media.url) == (
        "embed",
        "https://www.youtube.com/embed/a0cBLQndN8s",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123&t=42s",
        "https://youtu.be/abc123?si=x",
        "https://m.youtube.com/watch?v=abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/embed/abc123",
    ],
)
def test_youtube_embed_url_accepts_every_link_shape(url):
    assert youtube_embed_url(url) == "https://www.youtube.com/embed/abc123"


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/clip.mp4",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/@gooeyai",
        "https://youtu.be/",
    ],
)
def test_youtube_embed_url_rejects_anything_else(url):
    assert youtube_embed_url(url) is None


def test_no_media_at_all_leaves_the_slot_empty():
    page = object.__new__(VideoBotsPageV2)
    page.workflow = 0
    assert page._about_media(make_pr()) is None


def test_sdg_tiles_carry_the_un_icon_and_link():
    page = object.__new__(VideoBotsPageV2)
    tiles = page._about_sdgs(make_pr(sdgs=[1, 13]))
    assert [t.number for t in tiles] == [1, 13]
    assert tiles[0].title == "No Poverty"
    assert tiles[1].href == "https://sdgs.un.org/goals/goal13"
    assert tiles[1].icon_url.endswith("E_SDG_Icons-13.jpg")


def test_the_stat_rows_are_the_switch():
    """No separate toggle: adding a row shows the group, removing the last one hides it."""
    page = object.__new__(VideoBotsPageV2)
    pr = make_pr()
    pr.stats = SimpleNamespace(all=lambda: [])
    assert page._about_stats(pr) is None

    pr.stats = SimpleNamespace(
        all=lambda: [SimpleNamespace(value="1800+", label="Farmers supported")]
    )
    stats = page._about_stats(pr)
    assert stats.title == DEFAULT_STATS_TITLE
    assert [(c.value, c.label) for c in stats.cards] == [("1800+", "Farmers supported")]


def test_more_info_needs_both_a_url_and_a_label():
    page = object.__new__(VideoBotsPageV2)
    assert page._about_more_info(make_pr(more_info_url="/x")) is None
    assert page._about_more_info(make_pr(more_info_text="View case study")) is None
    link = page._about_more_info(
        make_pr(more_info_url="/x", more_info_text="View case study")
    )
    assert (link.href, link.text) == ("/x", "View case study")


def test_the_prompt_rides_inside_the_url_login_returns_to():
    """Appending to the login url itself would strand the prompt outside `next`, so it is
    added to the page url before that becomes `next`."""
    url = builder_prompt_next_url("https://gooey.ai/agent/", "Add a Hindi step")
    assert url.startswith("https://gooey.ai/agent/?")
    assert BUILDER_PROMPT_Q in url
    assert parse_qs(urlparse(url).query)[BUILDER_PROMPT_Q] == ["Add a Hindi step"]


def test_builder_prompt_url_keeps_existing_query_params():
    url = builder_prompt_next_url("https://gooey.ai/agent/?example_id=abc", "Hi")
    q = parse_qs(urlparse(url).query)
    assert q["example_id"] == ["abc"]
    assert q[BUILDER_PROMPT_Q] == ["Hi"]


def test_a_fully_dressed_about_page_serialises(monkeypatch):
    """Every marketing field set, rendered through the real component call - catches prop
    shape and pydantic validation that the per-method tests cannot."""
    page = object.__new__(VideoBotsPageV2)
    pr = make_pr(
        headline="Transforming Smallholder Farming",
        banner_url="https://cdn/banner.jpg",
        more_info_url="https://example.org/case-study",
        more_info_text="View case study",
        sdgs=[1, 13],
        stats_title="",
    )
    pr.workspace_id = None
    pr.notes = "An agri-advisor chatbot."
    pr.tags = SimpleNamespace(all=list)
    pr.stats = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(value="1800+", label="Farmers supported"),
            SimpleNamespace(value="17,000", label="User messages"),
        ]
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "current_pr", property(lambda self: pr), raising=False
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "_about_meta_groups", lambda self: [], raising=False
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "current_app_url", lambda self, tab=None: "/agent/"
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "is_logged_in", lambda self: False, raising=False
    )
    page._top_bar_integrations = lambda: []
    page.tab = None
    page.request = SimpleNamespace(user=None)
    gui.session_state.clear()

    root = RenderTreeNode("root")
    with NestingCtx(root):
        page._render_about_content()
    props = root.to_dict()["children"][0]["props"]

    assert props["headline"] == "Transforming Smallholder Farming"
    assert props["media"] == {"kind": "banner", "url": "https://cdn/banner.jpg"}
    assert props["more_info"] == {
        "text": "View case study",
        "href": "https://example.org/case-study",
    }
    assert [s["number"] for s in props["sdgs"]] == [1, 13]
    # blank stats_title falls back rather than rendering an empty heading
    assert props["stats"]["title"] == DEFAULT_STATS_TITLE
    assert [c["value"] for c in props["stats"]["cards"]] == ["1800+", "17,000"]


def test_anonymous_prompts_carry_a_login_url_that_replays_the_prompt():
    """Logged out each prompt goes through login; the prompt rides inside `next` so it comes
    back and replays."""
    page = object.__new__(VideoBotsPageV2)
    pr = make_pr()
    pr.builder_prompts = ["Add a Hindi step", "Make replies shorter"]
    page.current_pr = pr
    page.tab = None
    page.current_app_url = lambda tab=None: "https://gooey.ai/agent/"
    page.get_auth_url = lambda next_url=None: f"https://gooey.ai/login?next={next_url}"

    anon = _builder_prompts(page, is_anonymous=True)
    assert [s["text"] for s in anon] == ["Add a Hindi step", "Make replies shorter"]
    inner = unquote(parse_qs(urlparse(anon[0]["login_url"]).query)["next"][0])
    assert parse_qs(urlparse(inner).query)["builderprompt"] == ["Add a Hindi step"]

    # signed in there is nowhere to send them - the prompt posts straight to the builder
    assert all(
        s["login_url"] is None for s in _builder_prompts(page, is_anonymous=False)
    )


def test_only_four_prompts_are_ever_offered():
    page = object.__new__(VideoBotsPageV2)
    pr = make_pr()
    pr.builder_prompts = [f"q{i}" for i in range(9)]
    page.current_pr = pr
    page.tab = None
    page.current_app_url = lambda tab=None: "https://gooey.ai/agent/"
    page.get_auth_url = lambda next_url=None: "https://gooey.ai/login"
    assert len(_builder_prompts(page, is_anonymous=False)) == 4


def test_a_run_with_no_prompts_offers_none():
    page = object.__new__(VideoBotsPageV2)
    pr = make_pr()
    pr.builder_prompts = []
    page.current_pr = pr
    assert _builder_prompts(page, is_anonymous=False) == []
