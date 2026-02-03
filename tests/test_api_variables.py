from bots.models import get_default_published_run_workspace
from recipes.Translation import TranslationPage
from routers.api import create_new_run
from workspaces.models import Workspace


def _setup_root_state(page_cls, variables):
    pr = page_cls.get_root_pr()
    if variables is None:
        pr.saved_run.state.pop("variables", None)
    else:
        pr.saved_run.state["variables"] = variables
    pr.saved_run.save(update_fields=["state"])
    return pr.saved_run.state.copy()


def _build_request(page_cls, state):
    return page_cls.get_example_request(state)[1].copy()


def _create_run(page_cls, user, workspace, request_body):
    _, sr = create_new_run(
        page_cls=page_cls,
        query_params={},
        current_user=user,
        workspace=workspace,
        request_body=request_body,
    )
    sr.refresh_from_db()
    return sr


def test_create_new_run_merges_request_variables(db_fixtures, force_authentication):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    page_cls = TranslationPage

    state = _setup_root_state(page_cls, {"a": 1, "b": 1})
    request_body = _build_request(page_cls, state)
    request_body["variables"] = {"b": 2, "c": 3}

    sr = _create_run(page_cls, user, workspace, request_body)
    assert sr.state["variables"] == {"a": 1, "b": 2, "c": 3}


def test_create_new_run_preserves_variables_on_null(db_fixtures, force_authentication):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    page_cls = TranslationPage

    state = _setup_root_state(page_cls, {"a": 1, "b": 1})
    request_body = _build_request(page_cls, state)
    request_body["variables"] = None

    sr = _create_run(page_cls, user, workspace, request_body)
    assert sr.state["variables"] == {"a": 1, "b": 1}


def test_create_new_run_preserves_variables_on_empty_dict(
    db_fixtures, force_authentication
):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    page_cls = TranslationPage

    state = _setup_root_state(page_cls, {"a": 1, "b": 1})
    request_body = _build_request(page_cls, state)
    request_body["variables"] = {}

    sr = _create_run(page_cls, user, workspace, request_body)
    assert sr.state["variables"] == {"a": 1, "b": 1}


def test_create_new_run_preserves_variables_on_omitted(
    db_fixtures, force_authentication
):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    page_cls = TranslationPage

    state = _setup_root_state(page_cls, {"a": 1, "b": 1})
    request_body = _build_request(page_cls, state)
    request_body.pop("variables", None)

    sr = _create_run(page_cls, user, workspace, request_body)
    assert sr.state["variables"] == {"a": 1, "b": 1}


def test_create_new_run_sets_variables_when_state_missing(
    db_fixtures, force_authentication
):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    page_cls = TranslationPage

    state = _setup_root_state(page_cls, None)
    request_body = _build_request(page_cls, state)
    request_body["variables"] = {"a": 1}

    sr = _create_run(page_cls, user, workspace, request_body)
    assert sr.state["variables"] == {"a": 1}


def test_create_new_run_overwrites_only_overlapping_keys(
    db_fixtures, force_authentication
):
    user = force_authentication
    workspace = Workspace.objects.get(id=get_default_published_run_workspace())
    page_cls = TranslationPage

    state = _setup_root_state(page_cls, {"a": 1, "b": 1, "c": 1})
    request_body = _build_request(page_cls, state)
    request_body["variables"] = {"b": 2}

    sr = _create_run(page_cls, user, workspace, request_body)
    assert sr.state["variables"] == {"a": 1, "b": 2, "c": 1}
