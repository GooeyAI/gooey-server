import html
import re
from contextlib import nullcontext
from types import SimpleNamespace

import pydantic
import pytest
from furl import furl

import gooey_gui as gui
from fastapi import HTTPException

from daras_ai_v2 import icons, settings
from daras_ai_v2.base import BasePage as BasePageV1
from daras_ai_v2.tab_spec import TabSpec
from gooey_gui.types.recipe_top_bar_props import (
    LinkTarget,
    MenuIntent,
    RecipeTopBarProps,
    RecipeSubmitIntent,
    RunIntent,
    StopIntent,
    SubmitTarget,
    TopBarIntegration,
)
from gooey_gui.types.sidebar_props import SidebarProps
from gooey_gui.types.recipe_workspace_props import (
    PageShellConfig,
    RecipeWorkspacePanesProps,
    RecipeSurfaceProps,
    SingleLayout,
    SplitLayout,
    SurfaceId,
    WorkspacePaneControlProps,
    WorkspaceView,
    RecipeWorkspaceProps,
    RecipeWorkspaceTriggerProps,
)
from recipes.VideoBots import VideoBotsPage
from recipes.VideoBots_v2 import ConfigPane, VideoBotsPageV2
from routers.root import RecipeTabs


def test_video_bots_v2_uses_existing_celery_runner_class():
    assert VideoBotsPageV2.get_runner_page_cls() is VideoBotsPage


def test_video_bots_v2_schedules_legacy_celery_payload(monkeypatch):
    captured = {}
    task_result = SimpleNamespace(id="task-1")
    runner_task = SimpleNamespace(
        delay=lambda **kwargs: captured.update(kwargs) or task_result
    )
    monkeypatch.setattr("celeryapp.tasks.runner_task", runner_task)

    saved_fields = []
    saved_run = SimpleNamespace(
        run_id="run-1",
        uid="user-1",
        celery_task_id=None,
        save=lambda *, update_fields: saved_fields.extend(update_fields),
    )
    page = object.__new__(VideoBotsPageV2)
    page.request = SimpleNamespace(user=SimpleNamespace(id=123))
    page.realtime_channel_name = lambda run_id, uid: f"channel/{uid}/{run_id}"

    result = page.call_runner_task(
        saved_run,
        deduct_credits=False,
        unsaved_state={"input_prompt": "hello"},
    )

    assert result is task_result
    assert captured == {
        "page_cls": VideoBotsPage,
        "user_id": 123,
        "run_id": "run-1",
        "uid": "user-1",
        "channel": "channel/user-1/run-1",
        "unsaved_state": {"input_prompt": "hello"},
        "deduct_credits": False,
    }
    assert saved_run.celery_task_id == "task-1"
    assert saved_fields == ["celery_task_id", "updated_at"]


def test_video_bots_v2_inherits_business_logic():
    assert VideoBotsPageV2.create_new_run is VideoBotsPage.create_new_run
    assert VideoBotsPageV2.run_v2 is VideoBotsPage.run_v2
    assert VideoBotsPageV2.bind_tool is BasePageV1.bind_tool
    assert VideoBotsPageV2.render_steps is VideoBotsPage.render_steps
    assert (
        VideoBotsPageV2._render_regenerate_button
        is VideoBotsPage._render_regenerate_button
    )


def test_generated_v2_component_names_match_registry():
    assert {
        RecipeSurfaceProps._component,
        RecipeTopBarProps._component,
        RecipeWorkspacePanesProps._component,
        RecipeWorkspaceProps._component,
        RecipeWorkspaceTriggerProps._component,
        SidebarProps._component,
        WorkspacePaneControlProps._component,
    } == {
        "RecipeSurface",
        "RecipeTopBar",
        "RecipeWorkspacePanes",
        "RecipeWorkspace",
        "RecipeWorkspaceTrigger",
        "Sidebar",
        "WorkspacePaneControl",
    }


def test_workspace_panes_render_all_content_in_one_pass(monkeypatch):
    rendered = []
    components = []
    page = object.__new__(VideoBotsPageV2)

    monkeypatch.setattr(gui, "styled", lambda css: nullcontext())
    monkeypatch.setattr(gui, "div", lambda: nullcontext())
    monkeypatch.setattr(
        gui,
        "model_component",
        lambda props: components.append(props) or nullcontext(),
    )
    for method_name in (
        "_render_llm_instructions_pane",
        "_render_knowledge_pane",
        "_render_functions",
        "_render_settings_pane",
        "render_debug_pane",
    ):
        monkeypatch.setattr(
            VideoBotsPageV2,
            method_name,
            lambda self, name=method_name: rendered.append(name),
        )

    page._render_input_col()

    assert rendered == [
        "_render_llm_instructions_pane",
        "_render_knowledge_pane",
        "_render_functions",
        "_render_settings_pane",
        "render_debug_pane",
    ]
    assert components == [
        RecipeWorkspacePanesProps(
            panes=[
                {"id": "llm-instructions", "label": "LLM Instructions"},
                {"id": "knowledge", "label": "Knowledge"},
                {"id": "tools", "label": "Tools"},
                {"id": "settings", "label": "Settings"},
                {"id": "debug", "label": "Debug"},
            ]
        )
    ]


def test_layout_models_reject_extra_and_duplicate_surfaces():
    with pytest.raises(pydantic.ValidationError):
        SingleLayout(surface=SurfaceId.editor, typo=True)

    with pytest.raises(pydantic.ValidationError):
        SplitLayout(
            primary=SurfaceId.editor,
            secondary=SurfaceId.editor,
        )


def test_page_shell_rejects_undeclared_initial_layout():
    edit = SingleLayout(surface=SurfaceId.editor)
    split = SplitLayout(
        primary=SurfaceId.editor,
        secondary=SurfaceId.preview,
    )

    with pytest.raises(pydantic.ValidationError):
        PageShellConfig(
            storage_key="layout",
            initial_layout=SingleLayout(surface=SurfaceId.about),
            run_layout=split,
            views=[
                WorkspaceView(
                    key="edit",
                    label="Edit",
                    layout=edit,
                ),
                WorkspaceView(
                    key="split",
                    label="Split",
                    layout=split,
                ),
            ],
            workspace_href="/agent/",
            workspace_active=True,
        )


def test_page_shell_config_is_built_once_from_typed_layouts(monkeypatch):
    page = object.__new__(VideoBotsPageV2)
    page.tab = RecipeTabs.run
    page.request = SimpleNamespace(query_params={})
    split = SplitLayout(
        primary=SurfaceId.editor,
        secondary=SurfaceId.preview,
    )
    tabs = [
        TabSpec(
            key="split",
            label="Split",
            layout=split,
        )
    ]
    monkeypatch.setattr(
        VideoBotsPageV2,
        "_workspace_storage_key",
        lambda self: "layout",
    )
    monkeypatch.setattr(
        VideoBotsPageV2,
        "entry_layout",
        lambda self, specs: specs[0].layout,
    )
    monkeypatch.setattr(
        VideoBotsPageV2,
        "narrow_surface",
        lambda self: SurfaceId.preview,
    )
    monkeypatch.setattr(
        VideoBotsPageV2,
        "current_app_url",
        lambda self, tab: "/agent/",
    )
    monkeypatch.setattr(
        VideoBotsPageV2,
        "_is_run_in_progress",
        lambda self: False,
    )

    config = page._page_shell_config(tabs)

    assert config.initial_layout == split
    assert config.run_layout == split
    assert config.route_layout is None

    page.tab = RecipeTabs.preview
    page.request.query_params = {"run_id": "run-1"}
    preview_config = page._page_shell_config(tabs)

    assert preview_config.route_layout == SingleLayout(surface=SurfaceId.preview)
    assert preview_config.active_run_id == "run-1"


def test_view_only_reads_edit_permission_rather_than_authorship():
    """A workspace holds its apps in common, so a member with EDIT access is an editor of an
    app somebody else published, and a staff admin is an editor of every app. Reading
    `is_current_user_owner` asked who typed it in, which handed a member the presentation
    tabs on their own workspace's app.

    Both `can_edit_current_pr` and `current_sr_pr` are `cached_property`, so assigning to the
    instance is what a computed answer would have left behind.
    """
    page = object.__new__(VideoBotsPageV2)
    page.current_sr_pr = (SimpleNamespace(id=7), SimpleNamespace(saved_run_id=7))

    page.can_edit_current_pr = False
    assert page.is_view_only() is True

    page.can_edit_current_pr = True
    assert page.is_view_only() is False


def test_a_run_of_an_app_is_never_view_only():
    """The url has to point at the published run itself. A run of an app is the viewer's to
    work on and re-save as their own, whoever published the app it came from."""
    page = object.__new__(VideoBotsPageV2)
    page.current_sr_pr = (SimpleNamespace(id=7), SimpleNamespace(saved_run_id=99))

    page.can_edit_current_pr = False
    assert page.is_view_only() is False


def test_can_edit_current_pr_answers_false_without_a_user_or_workspace(monkeypatch):
    """The predicate is read while rendering every page, including logged-out ones, so it
    has to answer rather than raise."""
    from workspaces.models import Workspace

    page = object.__new__(VideoBotsPageV2)
    page.request = SimpleNamespace(user=None)
    assert page.can_edit_current_pr is False

    page = object.__new__(VideoBotsPageV2)
    page.request = SimpleNamespace(user=SimpleNamespace())
    monkeypatch.setattr(
        VideoBotsPageV2,
        "current_workspace",
        property(lambda self: (_ for _ in ()).throw(Workspace.DoesNotExist())),
    )
    assert page.can_edit_current_pr is False


def test_entry_layout_lands_on_the_tab_set_it_was_given(monkeypatch):
    """`is_view_only` picks both the tabs and the view they open on, so the two cannot
    disagree. A view-only viewer's tabs are About and How it works, and How it works is a
    config form they have no way to save - so About. Everyone who can update the app works,
    and folds to the preview on a phone."""
    about = SplitLayout(primary=SurfaceId.about, secondary=SurfaceId.preview)
    work = SplitLayout(primary=SurfaceId.editor, secondary=SurfaceId.preview)
    tabs = [TabSpec(key="about", label="About", layout=about)]

    page = object.__new__(VideoBotsPageV2)
    page.tab = RecipeTabs.run
    page.request = SimpleNamespace(query_params={})

    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: True)
    assert page.entry_layout(tabs) == about

    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: False)
    assert page.entry_layout(tabs) == work

    # The url has no say: whoever cannot update the app gets the view-only tab set, and so
    # lands where that tab set starts.
    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: True)
    page.request.query_params = {"run_id": "run-1"}
    assert page.entry_layout(tabs) == about

    page.request.query_params = {}
    page.tab = RecipeTabs.run_as_api
    assert page.entry_layout(tabs) == about


def test_document_tabs_drop_the_bootstrap_overflow_and_gutter_utilities():
    """Both are `!important`, so on API or Deploy they beat the one-axis scrolling and the
    gutter RecipeWorkspace.css gives a body with no workspace in it."""
    page = object.__new__(VideoBotsPageV2)

    workspace = page._workspace_body_class(SimpleNamespace(workspace_active=True))
    assert "overflow-auto" in workspace
    assert "px-0" in workspace

    document = page._workspace_body_class(SimpleNamespace(workspace_active=False))
    assert "overflow-auto" not in document
    assert "px-0" not in document
    assert "v2-workspace-body" in document


def test_submit_intent_is_discriminated_and_strict():
    adapter = pydantic.TypeAdapter(RecipeSubmitIntent)

    assert adapter.validate_json('{"kind":"run"}') == RunIntent()
    assert adapter.validate_json(
        '{"kind":"menu","item_key":"duplicate"}'
    ) == MenuIntent(item_key="duplicate")

    with pytest.raises(pydantic.ValidationError):
        adapter.validate_json('{"kind":"run","item_key":"duplicate"}')


def test_submit_intent_is_consumed_once():
    page = object.__new__(VideoBotsPageV2)
    gui.session_state[page.SUBMIT_INTENT_KEY] = '{"kind":"run"}'

    assert page._pop_submit_intent() == RunIntent()
    assert page._pop_submit_intent() is None


def test_about_deployment_cards_carry_the_chips_targets():
    """A channel card in About is the same action as its chip in the bar - a link where the
    chip navigates, and otherwise a submit carrying the intent that opens the chip's dialog,
    since the page's form posts its submitter's name and value."""
    page = object.__new__(VideoBotsPageV2)

    link = page._about_deployment_card(
        TopBarIntegration(
            key="web",
            label="Try in Web",
            icon_html="<i></i>",
            target=LinkTarget(href="/chat/agent/"),
        )
    )
    assert '<a class="v2-about-meta-card" href="/chat/agent/">' in link

    intent = MenuIntent(item_key="demo:7")
    submit = page._about_deployment_card(
        TopBarIntegration(
            key="demo:7",
            label="Try in WhatsApp",
            icon_html="<i></i>",
            target=SubmitTarget(intent=intent),
        )
    )
    assert 'type="submit"' in submit
    assert f'name="{page.SUBMIT_INTENT_KEY}"' in submit

    posted = re.search(r'value="([^"]*)"', submit).group(1)
    gui.session_state[page.SUBMIT_INTENT_KEY] = html.unescape(posted)
    assert page._pop_submit_intent() == intent


def test_every_about_card_is_drawn_from_one_body():
    """A deployment card and a config card are one object in the design, and were two copies
    of the same markup here - so a change to the card's shape reached one and not the other.
    Both go through `_about_meta_card_body` now.

    The chevron is what that shape gained: the cards link somewhere, and nothing on them said
    so. It is a constraint rather than a detail, because it is the affordance.
    """
    import json

    from gooey_gui.core.renderer import NestingCtx, RenderTreeNode

    page = object.__new__(VideoBotsPageV2)

    deployment = page._about_deployment_card(
        TopBarIntegration(
            key="web",
            label="Try in Web",
            icon_html="<i class='brand'></i>",
            target=LinkTarget(href="/chat/agent/"),
        )
    )

    root = RenderTreeNode("root")
    with NestingCtx(root):
        page._render_about_meta_card(
            icon="<i class='brand'></i>",
            label="GPT-5",
            pane=ConfigPane.llm_instructions,
        )
    config = json.dumps(root.to_dict())

    for markup, which in ((deployment, "deployment"), (config, "config")):
        assert "v2-about-meta-chevron" in markup, f"{which} card lost its chevron"
        # the mark and the chevron share a row, which is what puts them at opposite ends
        assert "v2-about-meta-head" in markup, f"{which} card lost its head row"
        assert "v2-about-meta-icon" in markup
        assert "v2-about-meta-label" in markup


def test_narrow_surface_keeps_the_editor_for_a_view_only_viewer(monkeypatch):
    """Their one work tab is "How it works", which exists to show the configuration - so a
    phone keeps the editor. An editor on Split keeps the bot."""
    page = object.__new__(VideoBotsPageV2)

    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: True)
    assert page.narrow_surface() == SurfaceId.editor

    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: False)
    assert page.narrow_surface() == SurfaceId.preview


def test_usage_is_kept_out_of_a_view_only_bar(monkeypatch):
    """A view-only viewer gets About and How it works, which present the workflow. A list of
    its runs is an editor's tool, so it does not belong beside them. Both rights are needed:
    updating the app, and belonging to the workspace whose runs the tab lists."""
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "can_view_usage", lambda self: True)
    monkeypatch.setattr(
        VideoBotsPageV2, "current_app_url", lambda self, tab: "/agent/usage/"
    )

    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: True)
    assert page._usage_href() is None

    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: False)
    assert page._usage_href() == "/agent/usage/"

    monkeypatch.setattr(VideoBotsPageV2, "can_view_usage", lambda self: False)
    assert page._usage_href() is None


def test_title_menu_offers_v1s_options(monkeypatch):
    """The chevron menu is v1's Options dialog, gated the same way."""
    from bots.models import WorkflowAccessLevel

    page = object.__new__(VideoBotsPageV2)
    pr = SimpleNamespace(
        is_root=lambda: False, saved_run="sr", tags=SimpleNamespace(all=list)
    )
    monkeypatch.setattr(VideoBotsPageV2, "is_logged_in", lambda self: True)
    monkeypatch.setattr(VideoBotsPageV2, "current_pr", property(lambda self: pr))
    monkeypatch.setattr(VideoBotsPageV2, "current_sr", property(lambda self: "sr"))
    monkeypatch.setattr(
        VideoBotsPageV2, "current_workspace", property(lambda self: None)
    )
    monkeypatch.setattr(
        WorkflowAccessLevel, "can_user_delete_published_run", lambda **kw: True
    )
    page.request = SimpleNamespace(user=object())

    labels = [item.label for item in page._title_menu_items()]
    assert labels == ["Versions", "Duplicate", "Delete"]

    # off an older version, duplicating means promoting that version to a new workflow
    monkeypatch.setattr(VideoBotsPageV2, "current_sr", property(lambda self: "older"))
    assert [i.label for i in page._title_menu_items()][1] == "Save as New"


def test_title_menu_is_empty_when_logged_out(monkeypatch):
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "is_logged_in", lambda self: False)
    assert page._title_menu_items() == []


def test_examples_route_redirects_to_the_explore_gallery_in_v2():
    """A v2 page has no Examples tab - it is not in the top bar, and v1's card grid is not
    what the shell renders - so the route hands off to explore, filtered to the workflow.

    302, not 301: the fork list grows as recipes migrate, and a permanent redirect would
    outlive a recipe's membership of it in every browser that cached it. No monkeypatch -
    the gate answers off `all_pages_v2`, so this exercises the real one."""
    from routers.root import examples_route

    render = examples_route.__wrapped__

    # the slug the tab is reached by, and an older one for the same recipe: one gallery
    resp = render(request=SimpleNamespace(), page_slug="agent")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/explore/?workflow=bots"

    resp = render(request=SimpleNamespace(), page_slug="video-bots")
    assert resp.headers["location"] == "/explore/?workflow=bots"

    # Opened from a published run, the tab still meant "show me the gallery": v1 filtered
    # `_examples_tab` on the workflow alone, so the run in the url never changed what was
    # rendered. It goes to the same gallery - redirecting back to the run would strip
    # `/examples/` and reload the page the user was already on.
    resp = render(
        request=SimpleNamespace(),
        page_slug="agent",
        run_slug="base-copilot-w-search-rag-code-execution",
        example_id="v1xm6uhp",
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/explore/?workflow=bots"


def test_examples_redirect_only_names_a_workflow_the_type_filter_can_hold(monkeypatch):
    """`gui.selectbox` swaps a value it has no option for for the blank one, which blanks the
    filter and bounces to the whole gallery - so the redirect either carries an option that
    exists or does not happen. Sweeps the v2 forks, so a recipe forked before it is listed
    on explore fails here rather than sending its Examples tab somewhere useless."""
    import routers.root
    from daras_ai_v2.all_pages_v2 import page_slug_map_v2
    from routers.root import examples_route
    from widgets import workflow_search

    filter_options = workflow_search.workflow_filter_slugs()
    assert filter_options, "no Type options at all - the check below would be vacuous"

    for slug, page_cls in page_slug_map_v2.items():
        resp = examples_route.__wrapped__(request=SimpleNamespace(), page_slug=slug)
        assert furl(resp.headers["location"]).args["workflow"] in filter_options, slug

    # and with no option to carry, the tab stays put rather than opening the whole gallery
    calls = []
    monkeypatch.setattr(
        routers.root,
        "render_recipe_page",
        lambda request, page_slug, tab, example_id: calls.append(page_slug),
    )
    monkeypatch.setattr(workflow_search, "workflow_filter_slugs", set)
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="agent")
    assert calls == ["agent"]


def test_examples_route_keeps_the_tab_wherever_the_page_is_v1(monkeypatch):
    """A v1 page's tab bar offers Examples and renders it in place, so only a recipe forked
    to v2 hands off. The fork is the whole decision - there is no user in it, so a logged
    out visitor and an admin get the same answer for the same slug."""
    import routers.root
    from routers.root import RecipeTabs, examples_route

    calls = []
    monkeypatch.setattr(
        routers.root,
        "render_recipe_page",
        lambda request, page_slug, tab, example_id: calls.append((page_slug, tab)),
    )

    # a recipe with no fork yet, a legacy api-only one, and an unknown slug that still needs
    # to reach the 404 the tab already raises
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="qr-code")
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="translate")
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="not-a-recipe")

    assert calls == [
        ("qr-code", RecipeTabs.examples),
        ("translate", RecipeTabs.examples),
        ("not-a-recipe", RecipeTabs.examples),
    ]

    # and with the flag off, even the fork keeps its v1 tab - the kill switch reaches here
    monkeypatch.setattr(settings, "ENABLE_LAYOUT_V2", False)
    calls.clear()
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="agent")
    assert calls == [("agent", RecipeTabs.examples)]


def test_the_menu_keys_python_stamps_are_the_ones_the_sheet_looks_for():
    """These three strings are declared twice - once here, once as literals in
    `RecipeTopBar/index.tsx` - because the mobile sheet reorders the title menu by key.

    The generated prop *types* are checked by CI, but nothing checks a value. Rename one in
    Python and the row silently vanishes from the phone menu: no type error, no failure,
    no log line. This is that missing check.
    """
    import re
    from pathlib import Path

    from daras_ai_v2.base_v2 import BasePage as BasePageV2

    source = Path("gooey-gui/app/components/RecipeTopBar/index.tsx").read_text()
    found = dict(re.findall(r'const (MENU_\w+?)_KEY = "([^"]+)";', source))
    assert found, "no menu key constants found - has the top bar been restructured?"

    expected = {
        "MENU_VERSION_HISTORY": BasePageV2.MENU_VERSION_HISTORY,
        "MENU_DUPLICATE": BasePageV2.MENU_DUPLICATE,
        "MENU_DELETE": BasePageV2.MENU_DELETE,
    }
    assert found == expected


def test_a_recipe_gets_the_base_tab_set_unless_it_says_otherwise(monkeypatch):
    """The base spec is the one every fork inherits, so Split has to be desktop-only *here*.
    It folds to a single pane below lg and the mobile sheet drops a desktop-only view -
    without the flag the next recipe to migrate gets a Split row in its phone menu.

    Also pins that VideoBots takes the base set rather than restating it: the two had
    already drifted on this very flag.
    """
    from recipes.VideoBots_v2 import VideoBotsPageV2

    monkeypatch.setattr(VideoBotsPageV2, "is_view_only", lambda self: False)
    tabs = VideoBotsPageV2.get_tab_spec(VideoBotsPageV2.__new__(VideoBotsPageV2))

    by_key = {tab.key: tab for tab in tabs}
    assert set(by_key) == {"about", "edit", "preview", "split"}
    assert by_key["split"].desktop_only is True
    assert not any(tab.desktop_only for key, tab in by_key.items() if key != "split"), (
        "only Split has nowhere to go below lg"
    )


def _headings_in(node) -> list[tuple[int, str]]:
    """Every heading the render tree emits, in document order, as (level, text).

    Two shapes to look for: `gui.tag("h2", ...)` becomes a `tag` node carrying the element
    name, and `gui.html("<h2 ...>")` carries the markup in its body.
    """
    import re

    found = []
    props = node.get("props") or {}
    element = props.get("__reactjsxelement") or ""
    if re.fullmatch(r"h[1-6]", element):
        found.append((int(element[1]), ""))
    for match in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>", props.get("body") or ""):
        found.append((int(match.group(1)), match.group(2)))
    for child in node.get("children") or []:
        found.extend(_headings_in(child))
    return found


def test_the_about_surface_carries_the_pages_one_h1(monkeypatch):
    """A recipe page had no `h1` at all - the workflow's name lived in a `span` in the top
    bar. The bar is chrome that repeats on every tab, so About is where the heading belongs:
    it is the surface that presents the workflow, and layout v2 renders it whatever pane is
    on screen.

    Visually hidden, because the bar already shows the name and About should not say it
    twice. Exactly one, which the always-render-three-surfaces design makes a real
    constraint rather than a convention - an `h1` added to the editor would ship a second
    one on every page.
    """
    from types import SimpleNamespace

    from gooey_gui.core.renderer import NestingCtx, RenderTreeNode

    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(
        VideoBotsPageV2,
        "current_pr",
        property(
            lambda self: SimpleNamespace(
                workspace_id=None, notes="", tags=SimpleNamespace(all=list)
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        VideoBotsPageV2,
        "_workflow_identity",
        lambda self: SimpleNamespace(name="Farmer.CHAT Ag Advisory Agent"),
    )
    for noop in (
        "_render_about_photo",
        "_render_about_meta",
        "_render_about_deployments",
    ):
        monkeypatch.setattr(VideoBotsPageV2, noop, lambda self, *a, **kw: None)

    root = RenderTreeNode("root")
    with NestingCtx(root):
        page._render_about_content()

    levels = [level for level, _ in _headings_in(root.to_dict())]
    assert levels.count(1) == 1, f"expected exactly one h1, got {levels}"


def test_about_section_titles_are_headings_rather_than_styled_divs(monkeypatch):
    """These name the sections of the page, so they are headings. They were `div`s, which
    left the whole About surface without a single one.

    The class stays: it already sets the size, weight and colour, so swapping the element
    changes the outline and nothing about the picture. The stylesheet carries a
    zero-specificity `:where()` reset that keeps the browser's heading scale out of it.
    """
    import json

    from gooey_gui.core.renderer import NestingCtx, RenderTreeNode

    page = object.__new__(VideoBotsPageV2)
    root = RenderTreeNode("root")
    with NestingCtx(root):
        page._render_about_meta_group(
            "Model", [(icons.sparkles, "GPT-5", ConfigPane.llm_instructions)]
        )

    assert _headings_in(root.to_dict()) == [(2, "Model")]
    # the shape it must never go back to
    assert '<div class=\\"v2-about-section-title\\"' not in json.dumps(root.to_dict())


def test_the_editor_surfaces_headings_do_not_skip_a_level(monkeypatch):
    """Capabilities was an `h4` with no `h2` or `h3` above it anywhere on the page, and the
    switches under it were `h5`. Nothing about the page's shape said those belonged to the
    editor rather than to About.

    Levels only - the wording is the recipe's to choose. `RecipeWorkspace.css` pins the two
    levels to the sizes `####` and `#####` used to render at, so the outline moved and the
    page did not.
    """
    import re
    from pathlib import Path

    source = Path("recipes/VideoBots_v2.py").read_text()
    levels = [
        len(m.group(1))
        for m in re.finditer(r'(?:gui\.markdown\(|label=)"(#+) ', source)
    ]
    assert levels, (
        "no markdown headings found - has the settings pane been restructured?"
    )
    assert min(levels) == 2, (
        f"the editor's top heading should be an h2, got h{min(levels)}"
    )
    for shallower, deeper in zip(levels, levels[1:]):
        assert deeper - shallower <= 1, f"h{shallower} -> h{deeper} skips a level"


def test_layout_v2_is_scoped_to_the_forked_recipes_and_asks_nothing_of_the_user():
    """The gate takes a slug, not a request: v2 is per-recipe, and every visitor - logged
    out included - gets the same layout for the same url.

    Sweeps `all_pages_v2` rather than naming slugs, so a recipe added to the fork list is
    covered here the day it lands. The v1 half names real recipes on purpose: those urls
    must keep answering in v1 whatever else changes."""
    from daras_ai_v2.all_pages import page_slug_map
    from daras_ai_v2.all_pages_v2 import page_slug_map_v2
    from daras_ai_v2.layout_v2 import can_use_layout_v2

    assert page_slug_map_v2, "no v2 forks at all - the sweep below would be vacuous"
    for slug in page_slug_map_v2:
        assert can_use_layout_v2(slug), slug

    for slug in ["qr-code", "translate", "not-a-recipe"]:
        assert not can_use_layout_v2(slug), slug

    # every recipe without a fork, so migrating one cannot quietly change another
    for slug in page_slug_map:
        if slug not in page_slug_map_v2:
            assert not can_use_layout_v2(slug), slug


def test_usage_is_404_on_a_recipe_with_no_v2_fork(monkeypatch):
    """v1's `render_selected_tab` has no case for this tab, so letting the route through
    would render chrome around an empty body. The 404 is what keeps that unreachable."""
    import routers.root
    from routers.root import RecipeTabs, usage_route

    calls = []
    monkeypatch.setattr(
        routers.root,
        "render_recipe_page",
        lambda request, page_slug, tab, example_id: calls.append((page_slug, tab)),
    )

    for slug in ["qr-code", "translate", "not-a-recipe"]:
        with pytest.raises(HTTPException) as excinfo:
            usage_route.__wrapped__(request=SimpleNamespace(), page_slug=slug)
        assert excinfo.value.status_code == 404, slug
    assert calls == [], "a page with no Usage tab still rendered one"

    # the fork does have the tab
    usage_route.__wrapped__(request=SimpleNamespace(), page_slug="agent")
    assert calls == [("agent", RecipeTabs.usage)]


def test_history_stays_per_recipe_outside_the_v2_forks(monkeypatch):
    """A v2 fork renames this tab Usage. Everything else keeps its own History rather than
    being sent to the global one: v2 is scoped per recipe, so this tab is too."""
    import routers.root
    from routers.root import RecipeTabs, history_route

    calls = []
    monkeypatch.setattr(
        routers.root,
        "render_recipe_page",
        lambda request, page_slug, tab, example_id: calls.append((page_slug, tab)),
    )

    history_route.__wrapped__(request=SimpleNamespace(), page_slug="agent")
    history_route.__wrapped__(request=SimpleNamespace(), page_slug="qr-code")
    history_route.__wrapped__(request=SimpleNamespace(), page_slug="translate")

    assert calls == [
        ("agent", RecipeTabs.usage),
        ("qr-code", RecipeTabs.history),
        ("translate", RecipeTabs.history),
    ]


def test_usage_carries_no_run_control(monkeypatch):
    """Usage reports on runs already made, so the bar offers no Run - and because it is left
    out rather than hidden, there is nothing to relocate into the editor's bottom run bar on
    a narrow screen either."""
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "_is_run_in_progress", lambda self: False)

    page.tab = RecipeTabs.usage
    assert page._top_bar_run_intent() is None

    page.tab = RecipeTabs.run
    assert page._top_bar_run_intent() == RunIntent()

    # a run in progress offers Stop, and still nothing on Usage
    monkeypatch.setattr(VideoBotsPageV2, "_is_run_in_progress", lambda self: True)
    assert page._top_bar_run_intent() == StopIntent()
    page.tab = RecipeTabs.usage
    assert page._top_bar_run_intent() is None


def test_usage_keeps_the_publish_control(monkeypatch):
    """Only Run comes out of the Usage bar. Publishing is not a thing you do to a run, so
    the tab has no say in the label - it stays permission-derived on every tab."""
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "is_logged_in", lambda self: True)
    monkeypatch.setattr(
        VideoBotsPageV2, "can_edit_current_pr", property(lambda self: True)
    )

    page.tab = RecipeTabs.usage
    assert page._top_bar_publish_label() == "Update"

    page.tab = RecipeTabs.run
    assert page._top_bar_publish_label() == "Update"


def test_the_bar_can_carry_no_run_control():
    """`run_intent` has to be omittable for Usage to drop Run - it was a required prop."""
    from gooey_gui.types.recipe_top_bar_props import RecipeTopBarProps

    field = RecipeTopBarProps.model_fields["run_intent"]
    assert not field.is_required(), "the bar has to be able to carry no run control"


def test_the_bar_names_the_published_run_a_saved_run_belongs_to(monkeypatch):
    """`parent` is the mobile sheet's way back to the published run, and by being present
    only on a saved run it is also how the sheet knows which of its three menus to draw.
    """
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(
        VideoBotsPageV2, "get_recipe_title", classmethod(lambda cls: "Copilot")
    )

    # the url points at the published run itself - no way back, there is nowhere back to
    page.current_sr_pr = (SimpleNamespace(id=7), SimpleNamespace(saved_run_id=7))
    assert page._top_bar_parent() is None

    # a saved run carries the title of the published run it belongs to
    pr = SimpleNamespace(
        saved_run_id=7,
        is_root=lambda: False,
        title="Farmer.AI",
        get_app_url=lambda: "/agent/farmer-ai-xyz/",
    )
    page.current_sr_pr = (SimpleNamespace(id=99), pr)
    parent = page._top_bar_parent()
    assert (parent.label, parent.href) == ("Farmer.AI", "/agent/farmer-ai-xyz/")

    # a saved run of a root recipe falls back to the recipe, which is what it forked from
    root_pr = SimpleNamespace(
        saved_run_id=7,
        is_root=lambda: True,
        title="",
        get_app_url=lambda: "/agent/",
    )
    page.current_sr_pr = (SimpleNamespace(id=99), root_pr)
    assert page._top_bar_parent().label == "Copilot"


def test_the_builder_panel_is_hosted_only_beside_the_workspace(monkeypatch):
    """Deploy, API and Usage have no workspace for the panel to sit next to, and Deploy's
    web preview breaks outright when it takes half the width. They still offer the way in:
    availability stays tab-blind, or the mobile sheet would lose the row that navigates to
    the workspace and opens it there."""
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "_can_launch_builder", lambda self: True)

    for tab in (RecipeTabs.run, RecipeTabs.preview):
        page.tab = tab
        assert page._is_workspace_tab() is True, tab.name
        assert page._hosts_builder() is True, tab.name

    for tab in (RecipeTabs.integrations, RecipeTabs.run_as_api, RecipeTabs.usage):
        page.tab = tab
        assert page._is_workspace_tab() is False, tab.name
        assert page._hosts_builder() is False, tab.name


def test_the_workspace_alone_does_not_host_an_unavailable_builder(monkeypatch):
    """Hosting is availability *and* the tab - a logged-out visitor gets no panel anywhere."""
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "_can_launch_builder", lambda self: False)

    page.tab = RecipeTabs.run
    assert page._hosts_builder() is False


def test_about_names_what_else_the_owner_has_published(monkeypatch):
    """The line qualifies the *name* it sits under, so it reports what else that workspace
    has published rather than how much this one workflow has been run. This workflow's own
    run count is on its explore card and in the bar's cost cluster.

    Read through `public_workflow_count`, so the number under a workspace's name here is the
    same one its profile page shows - two counts of "how many workflows" would drift.
    """
    from daras_ai_v2 import profiles

    page = object.__new__(VideoBotsPageV2)
    counted = []

    def fake_count(workspace):
        counted.append(workspace)
        return fake_count.value

    monkeypatch.setattr(profiles, "public_workflow_count", fake_count)

    workspace = SimpleNamespace()
    pr = SimpleNamespace(workspace_id=7, workspace=workspace)

    fake_count.value = 1
    assert page._about_author_subtitle(pr) == "1 Published workflow"
    fake_count.value = 12
    assert page._about_author_subtitle(pr) == "12 Published workflows"
    # the same suffixes the cards use, so a prolific workspace does not read as a phone number
    fake_count.value = 1500
    assert page._about_author_subtitle(pr) == "1.5K Published workflows"

    # it is the *workspace* that is counted, not the run
    assert counted and all(w is workspace for w in counted)

    # nothing to report: the line is left off rather than reading "0 Published workflows"
    fake_count.value = 0
    assert page._about_author_subtitle(pr) == ""
    # ...and an unowned run never reaches the query at all
    counted.clear()
    fake_count.value = 12
    assert page._about_author_subtitle(SimpleNamespace(workspace_id=None)) == ""
    assert counted == []
