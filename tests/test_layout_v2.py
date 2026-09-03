import html
import re
from types import SimpleNamespace

import pydantic
import pytest
from furl import furl

import gooey_gui as gui
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
from recipes.VideoBots_v2 import VideoBotsPageV2
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
        RecipeWorkspaceProps._component,
        RecipeWorkspaceTriggerProps._component,
        SidebarProps._component,
        WorkspacePaneControlProps._component,
    } == {
        "RecipeSurface",
        "RecipeTopBar",
        "RecipeWorkspace",
        "RecipeWorkspaceTrigger",
        "Sidebar",
        "WorkspacePaneControl",
    }


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


def test_examples_route_redirects_to_the_explore_gallery_in_v2(monkeypatch):
    """A v2 page has no Examples tab - it is not in the top bar, and v1's card grid is not
    what the shell renders - so the route hands off to explore, filtered to the workflow.
    302, not 301: which page you get depends on the user."""
    import daras_ai_v2.layout_v2
    from routers.root import examples_route

    monkeypatch.setattr(
        daras_ai_v2.layout_v2, "can_use_layout_v2", lambda request: True
    )
    render = examples_route.__wrapped__

    # the slug the tab is reached by, and an older one for the same recipe: one gallery
    resp = render(request=SimpleNamespace(), page_slug="agent")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/explore/?workflow=bots"

    resp = render(request=SimpleNamespace(), page_slug="video-bots")
    assert resp.headers["location"] == "/explore/?workflow=bots"


def test_examples_redirect_only_names_a_workflow_the_type_filter_can_hold(monkeypatch):
    """`gui.selectbox` swaps a value it has no option for for the blank one, which blanks the
    filter and bounces to the whole gallery - so the redirect either carries an option that
    exists or does not happen. Sweeps the v2 forks, so a recipe forked before it is listed
    on explore fails here rather than sending its Examples tab somewhere useless."""
    import daras_ai_v2.layout_v2
    import routers.root
    from daras_ai_v2.all_pages_v2 import page_slug_map_v2
    from routers.root import examples_route
    from widgets import workflow_search

    monkeypatch.setattr(
        daras_ai_v2.layout_v2, "can_use_layout_v2", lambda request: True
    )
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
    to v2 hands off. The flag alone is not enough - it is on for every recipe an admin
    opens, while the fork is what decides which layout the page is drawn in."""
    import daras_ai_v2.layout_v2
    import routers.root
    from routers.root import RecipeTabs, examples_route

    calls = []
    monkeypatch.setattr(
        routers.root,
        "render_recipe_page",
        lambda request, page_slug, tab, example_id: calls.append((page_slug, tab)),
    )

    monkeypatch.setattr(
        daras_ai_v2.layout_v2, "can_use_layout_v2", lambda request: False
    )
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="agent")

    monkeypatch.setattr(
        daras_ai_v2.layout_v2, "can_use_layout_v2", lambda request: True
    )
    # v2 is on, but these render in v1: a recipe with no fork yet, a legacy api-only one,
    # and an unknown slug that still needs to reach the 404 the tab already raises
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="qr-code")
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="translate")
    examples_route.__wrapped__(request=SimpleNamespace(), page_slug="not-a-recipe")

    assert calls == [
        ("agent", RecipeTabs.examples),
        ("qr-code", RecipeTabs.examples),
        ("translate", RecipeTabs.examples),
        ("not-a-recipe", RecipeTabs.examples),
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
