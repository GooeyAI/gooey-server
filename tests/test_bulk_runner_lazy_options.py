import types

import pytest

from recipes.BulkRunner import BulkRunnerPage


class NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_bulk_runner_selected_workflow_row_defers_shared_options(monkeypatch):
    from daras_ai_v2 import all_pages, workflow_url_input
    from recipes import BulkRunner

    calls = []
    row = {
        "workflow": 4,
        "url": "https://gooey.ai/copilot/example/",
        "--added_workflows": {
            "https://gooey.ai/copilot/example/": "Selected Copilot",
        },
    }
    page = BulkRunnerPage(request=types.SimpleNamespace(user=None))

    monkeypatch.setattr(
        all_pages,
        "all_home_pages",
        [types.SimpleNamespace(workflow=4, get_recipe_title=lambda: "Copilot")],
    )
    monkeypatch.setattr(BulkRunner.gui, "session_state", {})
    monkeypatch.setattr(
        BulkRunner.gui,
        "columns",
        lambda widths, **kwargs: [NoopContext() for _ in widths],
    )
    monkeypatch.setattr(BulkRunner.gui, "div", lambda *args, **kwargs: NoopContext())
    monkeypatch.setattr(
        BulkRunner.gui,
        "selectbox",
        lambda label, key, options, **kwargs: calls.append(
            ("selectbox", key, list(options), kwargs)
        )
        or (4 if key.endswith(":workflow") else row["url"]),
    )
    monkeypatch.setattr(
        BulkRunner, "edit_button", lambda key: calls.append(("edit", key))
    )
    monkeypatch.setattr(
        BulkRunner.gui, "url_button", lambda url: calls.append(("url", url))
    )
    monkeypatch.setattr(
        BulkRunner, "del_button", lambda key: calls.append(("delete", key))
    )
    monkeypatch.setattr(
        BulkRunner, "url_to_runs", lambda url: calls.append(("resolve", url))
    )
    monkeypatch.setattr(
        workflow_url_input,
        "get_published_run_selectbox_props",
        lambda **kwargs: (
            {row["url"]: "Selected Copilot"},
            {
                "asyncOptionsUrl": "/__/published-run-options/?page_slug=copilot",
                "nextOptionsPage": 0,
            },
        ),
    )

    page.render_run_url_inputs("row-key", "delete-key", row)

    selectbox_calls = [call for call in calls if call[:2] == ("selectbox", "row-key")]
    assert selectbox_calls
    assert selectbox_calls[0][2] == [row["url"]]
    assert selectbox_calls[0][3]["nextOptionsPage"] == 0
    assert selectbox_calls[0][3]["asyncOptionsUrl"]
    assert ("edit", "row-key") in calls
    assert ("url", row["url"]) in calls
    assert ("delete", "delete-key") in calls


def test_workflow_url_input_selected_row_defers_shared_options(monkeypatch):
    from daras_ai_v2 import workflow_url_input

    calls = []
    row = {
        "workflow": 4,
        "url": "https://gooey.ai/eval/example/",
        "--added_workflows": {
            "https://gooey.ai/eval/example/": "Selected Eval",
        },
    }

    monkeypatch.setattr(workflow_url_input.gui, "session_state", {})
    monkeypatch.setattr(
        workflow_url_input.gui, "div", lambda *args, **kwargs: NoopContext()
    )
    monkeypatch.setattr(
        workflow_url_input.gui,
        "selectbox",
        lambda label, key, options, **kwargs: calls.append(
            ("selectbox", key, list(options), kwargs)
        )
        or row["url"],
    )
    monkeypatch.setattr(
        workflow_url_input, "edit_button", lambda key: calls.append(("edit", key))
    )
    monkeypatch.setattr(
        workflow_url_input.gui, "url_button", lambda url: calls.append(("url", url))
    )
    monkeypatch.setattr(
        workflow_url_input, "del_button", lambda key: calls.append(("delete", key))
    )
    monkeypatch.setattr(
        workflow_url_input, "url_to_runs", lambda url: ("page", "sr", "pr")
    )
    monkeypatch.setattr(
        workflow_url_input,
        "get_published_run_selectbox_props",
        lambda **kwargs: (
            {row["url"]: "Selected Eval"},
            {
                "asyncOptionsUrl": "/__/published-run-options/?page_slug=example",
                "nextOptionsPage": 0,
            },
        ),
    )

    ret = workflow_url_input.workflow_url_input(
        page_cls=types.SimpleNamespace(workflow=4, slug_versions=["example"]),
        key="row-key",
        internal_state=row,
        del_key="delete-key",
    )

    assert ret == ("page", "sr", "pr")
    selectbox_calls = [call for call in calls if call[:2] == ("selectbox", "row-key")]
    assert selectbox_calls
    assert selectbox_calls[0][2] == [row["url"]]
    assert selectbox_calls[0][3]["nextOptionsPage"] == 0
    assert selectbox_calls[0][3]["asyncOptionsUrl"]
    assert ("edit", "row-key") in calls
    assert ("url", row["url"]) in calls
    assert ("delete", "delete-key") in calls


def test_published_run_options_search_filters_before_paginating(monkeypatch):
    from daras_ai_v2 import published_run_options

    page_cls = types.SimpleNamespace(workflow=4)
    runs = [
        make_published_run("https://gooey.ai/copilot/first/"),
        make_published_run("https://gooey.ai/copilot/second/"),
        make_published_run("https://gooey.ai/copilot/third/"),
    ]
    labels = {
        "https://gooey.ai/copilot/first/": "First",
        "https://gooey.ai/copilot/second/": "Second",
        "https://gooey.ai/copilot/third/": "Third Match",
    }
    monkeypatch.setattr(
        published_run_options,
        "get_published_runs_options_queryset",
        lambda page_cls, current_user: mock_runs_queryset(runs),
    )
    monkeypatch.setattr(
        published_run_options,
        "get_title_breadcrumbs",
        lambda page_cls, sr, pr: types.SimpleNamespace(
            title_with_prefix=lambda: labels[pr.get_app_url()]
        ),
    )

    options, next_page = published_run_options.get_published_run_options_page(
        page_cls=page_cls,
        include_root=False,
        q="third",
        page_size=2,
    )

    assert options == {"https://gooey.ai/copilot/third/": "Third Match"}
    assert next_page is None


def test_published_run_options_search_paginates_filtered_results(monkeypatch):
    from daras_ai_v2 import published_run_options

    page_cls = types.SimpleNamespace(workflow=4)
    runs = [
        make_published_run("https://gooey.ai/copilot/one/"),
        make_published_run("https://gooey.ai/copilot/nope/"),
        make_published_run("https://gooey.ai/copilot/two/"),
        make_published_run("https://gooey.ai/copilot/three/"),
    ]
    labels = {
        "https://gooey.ai/copilot/one/": "Match One",
        "https://gooey.ai/copilot/nope/": "Nope",
        "https://gooey.ai/copilot/two/": "Match Two",
        "https://gooey.ai/copilot/three/": "Match Three",
    }
    monkeypatch.setattr(
        published_run_options,
        "get_published_runs_options_queryset",
        lambda page_cls, current_user: mock_runs_queryset(runs),
    )
    monkeypatch.setattr(
        published_run_options,
        "get_title_breadcrumbs",
        lambda page_cls, sr, pr: types.SimpleNamespace(
            title_with_prefix=lambda: labels[pr.get_app_url()]
        ),
    )

    first_page, next_page = published_run_options.get_published_run_options_page(
        page_cls=page_cls,
        include_root=False,
        q="match",
        page_size=2,
    )
    second_page, final_page = published_run_options.get_published_run_options_page(
        page_cls=page_cls,
        include_root=False,
        q="match",
        page=next_page,
        page_size=2,
    )

    assert list(first_page.values()) == ["Match One", "Match Two"]
    assert next_page == 1
    assert list(second_page.values()) == ["Match Three"]
    assert final_page is None


def test_selected_run_option_label_recovers_from_url(monkeypatch):
    from daras_ai_v2 import workflow_url_input

    page_cls = types.SimpleNamespace(workflow=4)
    selected_url = "https://gooey.ai/copilot/lazy-option/"
    monkeypatch.setattr(
        workflow_url_input,
        "url_to_runs",
        lambda url: (page_cls, "saved-run", "published-run"),
    )
    monkeypatch.setattr(
        workflow_url_input,
        "get_title_breadcrumbs",
        lambda page_cls, sr, pr: types.SimpleNamespace(
            title_with_prefix=lambda: "Recovered Label"
        ),
    )

    label = workflow_url_input.get_selected_run_option_label(
        page_cls=page_cls,
        selected_url=selected_url,
    )

    assert label == "Recovered Label"


def test_get_published_run_selectbox_props_merges_added_workflows(monkeypatch):
    from daras_ai_v2 import workflow_url_input

    page_cls = types.SimpleNamespace(
        workflow=4,
        slug_versions=["copilot"],
    )
    selected_url = "https://gooey.ai/copilot/selected/"
    extra_url = "https://gooey.ai/copilot/custom/"
    monkeypatch.setattr(
        workflow_url_input,
        "get_selected_run_option_label",
        lambda **kwargs: "Selected",
    )

    options, async_props = workflow_url_input.get_published_run_selectbox_props(
        page_cls=page_cls,
        selected_url=selected_url,
        selected_options={
            selected_url: "Selected",
            extra_url: "Custom Run",
        },
        lazy_options=True,
    )

    assert options[selected_url] == "Selected"
    assert options[extra_url] == "Custom Run"
    assert async_props["nextOptionsPage"] == 0
    assert "/__/published-run-options/" in async_props["asyncOptionsUrl"]


def test_get_published_run_selectbox_props_non_lazy_omits_async(monkeypatch):
    from daras_ai_v2 import workflow_url_input

    page_cls = types.SimpleNamespace(workflow=4, slug_versions=["copilot"])
    monkeypatch.setattr(
        workflow_url_input,
        "get_cached_all_published_run_options",
        lambda **kwargs: {"https://gooey.ai/copilot/example/": "Example"},
    )

    options, async_props = workflow_url_input.get_published_run_selectbox_props(
        page_cls=page_cls,
        lazy_options=False,
    )

    assert options == {"https://gooey.ai/copilot/example/": "Example"}
    assert async_props == {}


def test_published_run_options_api(monkeypatch):
    from starlette.testclient import TestClient

    from daras_ai_v2 import all_pages
    from routers import published_run_options
    from server import app

    page_cls = all_pages.all_api_pages[0]
    slug = page_cls.slug_versions[-1]
    monkeypatch.setattr(
        published_run_options,
        "get_selectable_workflow_page_cls",
        lambda page_slug: page_cls,
    )
    monkeypatch.setattr(
        published_run_options,
        "get_published_run_options_page",
        lambda **kwargs: (
            {"https://gooey.ai/example/": "Example"},
            None,
        ),
    )

    response = TestClient(app).get(
        f"/__/published-run-options/?page_slug={slug}&page=0"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["options"] == [
        {"value": "https://gooey.ai/example/", "label": "Example"}
    ]
    assert data["nextOptionsPage"] is None


def test_selected_run_option_label_falls_back_on_resolve_error(monkeypatch):
    from daras_ai_v2 import workflow_url_input

    page_cls = types.SimpleNamespace(workflow=4)
    selected_url = "https://gooey.ai/copilot/broken/"

    def raise_error(url):
        raise KeyError("bad url")

    monkeypatch.setattr(workflow_url_input, "url_to_runs", raise_error)

    label = workflow_url_input.get_selected_run_option_label(
        page_cls=page_cls,
        selected_url=selected_url,
    )

    assert label == selected_url


def test_get_selectable_workflow_page_cls_excludes_hidden_pages():
    from daras_ai_v2 import all_pages
    from daras_ai_v2.published_run_options import get_selectable_workflow_page_cls

    for page_cls in all_pages.all_api_pages:
        slug = page_cls.slug_versions[-1]
        assert get_selectable_workflow_page_cls(slug) is page_cls

    for hidden_page_cls in all_pages.all_hidden_pages:
        if hidden_page_cls in all_pages.all_api_pages:
            continue
        for slug in hidden_page_cls.slug_versions:
            with pytest.raises(KeyError):
                get_selectable_workflow_page_cls(slug)


def make_published_run(url: str):
    return types.SimpleNamespace(
        saved_run=types.SimpleNamespace(),
        get_app_url=lambda: url,
    )


def mock_runs_queryset(runs):
    class MockQueryset:
        def iterator(self):
            return iter(runs)

    return MockQueryset()
