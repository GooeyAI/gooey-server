import html
import re
from types import SimpleNamespace

import pydantic
import pytest

import gooey_gui as gui
from daras_ai_v2.base import BasePage as BasePageV1
from daras_ai_v2.tab_spec import TabSpec
from gooey_gui.types.recipe_top_bar_props import (
    LinkTarget,
    MenuIntent,
    RecipeTopBarProps,
    RecipeSubmitIntent,
    RunIntent,
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


def test_entry_layout_lands_on_the_tab_set_it_was_given(monkeypatch):
    """`is_unowned_example` picks both the tabs and the view they open on, so the two cannot
    disagree. A visitor's tabs are About and How it works, and How it works is a config form
    they have no way to save - so About. Everyone else works, and folds to the preview on a
    phone."""
    about = SplitLayout(primary=SurfaceId.about, secondary=SurfaceId.preview)
    work = SplitLayout(primary=SurfaceId.editor, secondary=SurfaceId.preview)
    tabs = [TabSpec(key="about", label="About", layout=about)]

    page = object.__new__(VideoBotsPageV2)
    page.tab = RecipeTabs.run
    page.request = SimpleNamespace(query_params={})

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: True)
    assert page.entry_layout(tabs) == about

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: False)
    assert page.entry_layout(tabs) == work

    # The url has no say: an admin reading somebody else's published run is a visitor to it,
    # gets their tab set, and so lands where that tab set starts.
    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: True)
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


def test_narrow_surface_keeps_the_editor_for_a_visitor(monkeypatch):
    """A visitor's one work tab is "How it works", which exists to show the configuration -
    so a phone keeps the editor. An owner on Split keeps the bot."""
    page = object.__new__(VideoBotsPageV2)

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: True)
    assert page.narrow_surface() == SurfaceId.editor

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: False)
    assert page.narrow_surface() == SurfaceId.preview


def test_usage_is_kept_out_of_a_visitors_bar(monkeypatch):
    """A visitor gets About and How it works, which present the workflow. A list of its runs
    is an owner's tool, so it does not belong beside them - even for an admin, who may read
    the run data of an app that is not theirs."""
    page = object.__new__(VideoBotsPageV2)
    monkeypatch.setattr(VideoBotsPageV2, "can_view_usage", lambda self: True)
    monkeypatch.setattr(
        VideoBotsPageV2, "current_app_url", lambda self, tab: "/agent/usage/"
    )

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: True)
    assert page._usage_href() is None

    monkeypatch.setattr(VideoBotsPageV2, "is_unowned_example", lambda self: False)
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
