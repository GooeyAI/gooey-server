from __future__ import annotations

import typing

import gooey_gui as gui
import requests

from .composio_tools import get_toolkit_name_by_slug
from .models import FunctionScopes, ScopeParts
from app_users.models import AppUser
from bots.models import PublishedRun
from daras_ai_v2 import settings


if typing.TYPE_CHECKING:
    from workspaces.models import Workspace


def get_integration_authorizations_for_workspace(workspace: "Workspace"):
    r = requests.get(
        "https://backend.composio.dev/api/v3/connected_accounts",
        headers={
            "x-api-key": str(settings.COMPOSIO_API_KEY),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "statuses": ["ACTIVE"],
            "limit": 10_000,
        },
    )
    r.raise_for_status()

    data = r.json()

    workspace_user_id = FunctionScopes.get_user_id_for_scope(
        scope=FunctionScopes.workspace,
        workspace=workspace,
        user=None,
        published_run=None,
    )
    workspace_prefix = workspace_user_id + "/"
    for item in data.get("items", []):
        if item["user_id"] == workspace_user_id or item["user_id"].startswith(
            workspace_prefix
        ):
            match FunctionScopes.from_user_id(item["user_id"]):
                case None:
                    continue
                case scope, values:
                    yield item, scope, values


def manage_integration_authorizations(workspace: Workspace, current_user: AppUser):
    gui.caption("""
        Integrations use saved authorizations to securely connect your Gooey.AI workflows with other platforms (Google/M365, Notion, Slack, and more). The Authorized for scope defines how broadly the authorization may be used across your Workspace, Deployments and Users. [Learn more](https://gooey.ai/IntegrationAuthorizationHelp).
    """)

    account_scopes = list(
        get_integration_authorizations_for_workspace(workspace=workspace)
    )
    if not account_scopes:
        gui.write("No integrations authorized yet.")
        return

    with gui.div(className="table-responsive"), gui.tag("table", className="table"):
        with gui.tag("thead"), gui.tag("tr"):
            with gui.tag("th", scope="col"):
                gui.html("Workflow")
            with gui.tag("th", scope="col"):
                gui.html("Integration")
            with gui.tag("th", scope="col"):
                gui.html("Authorized for")

        with gui.tag("tbody"):
            pr_ids, user_ids = set(), set()
            for _, _, scope_parts in account_scopes:
                if pr_id := scope_parts.get(ScopeParts.saved_workflow):
                    pr_ids.add(pr_id)
                if user_id := scope_parts.get(ScopeParts.member):
                    user_ids.add(user_id)
            published_runs = (
                pr_ids
                and {
                    pr.published_run_id: pr
                    for pr in PublishedRun.objects.filter(published_run_id__in=pr_ids)
                }
                or {}
            )
            users = (
                user_ids
                and {user.id: user for user in AppUser.objects.filter(id__in=user_ids)}
                or {}
            )

            for account, scope, scope_parts in account_scopes:
                toolkit_name = get_toolkit_name_by_slug(account["toolkit"]["slug"])
                published_run_id = scope_parts.get(ScopeParts.saved_workflow)
                published_run = (
                    published_run_id and published_runs.get(published_run_id) or None
                )
                user_id = scope_parts.get(ScopeParts.member)
                user = user_id and users.get(int(user_id)) or None

                with gui.tag("tr", className="align-middle"):
                    with gui.tag("td"):
                        if published_run:
                            with gui.link(to=published_run.get_app_url()):
                                gui.write(
                                    published_run.title,
                                    className="container-margin-reset",
                                )
                        else:
                            gui.html(
                                f'All {workspace.html_icon()} <h6 class="d-inline">{workspace.display_name(current_user=current_user)}</h6> Workflows'
                            )
                    with gui.tag("td"):
                        gui.html(toolkit_name)
                    with gui.tag("td"):
                        gui.html(
                            FunctionScopes.format_label(
                                name=scope.name,
                                workspace=workspace,
                                user=user,
                                published_run=published_run,
                                current_user=current_user,
                            )
                        )
