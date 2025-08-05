import typing
from contextlib import contextmanager
from enum import Enum

import gooey_gui as gui
from django.db.models import Q
from fastapi.requests import Request
from furl import furl
from loguru import logger
from requests.models import HTTPError
from starlette.exceptions import HTTPException

from bots.models import PublishedRun, WorkflowAccessLevel, Workflow
from daras_ai_v2 import icons, paypal
from daras_ai_v2.billing import billing_page
from daras_ai_v2.fastapi_tricks import get_app_route_url, get_route_path
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.profiles import edit_user_profile_page
from daras_ai_v2.urls import paginate_queryset, paginate_button
from managed_secrets.widgets import manage_secrets_table
from payments.webhooks import PaypalWebhookHandler
from routers.custom_api_router import CustomAPIRouter
from routers.root import explore_page, page_wrapper, get_og_url_path
from widgets.saved_workflow import render_saved_workflow_preview
from workspaces.models import Workspace, WorkspaceInvite
from workspaces.views import invitation_page, workspaces_page
from workspaces.widgets import get_current_workspace, SWITCH_WORKSPACE_KEY
from widgets.sidebar import sidebar_logo_header

if typing.TYPE_CHECKING:
    from app_users.models import AppUser

app = CustomAPIRouter()


@gui.route(app, "/payment-processing/")
def payment_processing_route(
    request: Request, provider: str | None = None, subscription_id: str | None = None
):
    waiting_time_sec = 3
    subtext = None

    if provider == "paypal":
        success = gui.run_in_thread(
            threaded_paypal_handle_subscription_updated,
            args=[subscription_id],
        )
        if success:
            # immediately redirect
            waiting_time_sec = 0
        else:
            # either failed or still running. in either case, wait 30s before redirecting
            waiting_time_sec = 30
            subtext = (
                "PayPal transactions take up to a minute to reflect in your account"
            )

    with page_wrapper(request, className="m-auto"):
        with gui.center():
            with gui.div(className="d-flex align-items-center"):
                gui.div(
                    className="gooey-spinner me-4",
                    style=dict(height="3rem", width="3rem"),
                )
                gui.write("# Processing payment...")

            if subtext:
                gui.caption(subtext)

    gui.js(
        # language=JavaScript
        """
        setTimeout(() => {
            gui.navigate(redirectUrl);
        }, waitingTimeMs);
        """,
        waitingTimeMs=waiting_time_sec * 1000,
        redirectUrl=get_route_path(account_route),
    )

    return dict(
        meta=raw_build_meta_tags(url=str(request.url), title="Processing Payment...")
    )


@gui.route(app, "/account")
def old_account_route(request: Request):
    if next_url := request.query_params.get("next"):
        query_params = dict(next=next_url)
    else:
        query_params = None
    raise gui.RedirectException(
        furl(get_route_path(account_route), query_params=query_params)
    )


@gui.route(app, "/account/billing")
def account_route(request: Request):
    with account_page_wrapper(request, AccountTabs.billing) as current_workspace:
        billing_tab(request, current_workspace)
    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url,
            canonical_url=url,
            title="Billing • Gooey.AI",
            description="Your billing details.",
            robots="noindex,nofollow",
        )
    )


@gui.route(app, "/account/profile/")
def profile_route(request: Request):
    is_switching_workspace = gui.session_state.get(SWITCH_WORKSPACE_KEY)
    with account_page_wrapper(request, AccountTabs.profile) as current_workspace:
        if not current_workspace.is_personal:
            if is_switching_workspace:
                raise gui.RedirectException(get_route_path(members_route))
            else:
                gui.session_state[SWITCH_WORKSPACE_KEY] = str(
                    request.user.get_or_create_personal_workspace()[0].id
                )
                gui.rerun()
        profile_tab(request, current_workspace)
    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url,
            canonical_url=url,
            title="Profile • Gooey.AI",
            description="Your profile details.",
            robots="noindex,nofollow",
        )
    )


@gui.route(app, "/saved")
def explore_in_current_workspace(request: Request):
    from widgets.workflow_search import SearchFilters, get_filter_value_from_workspace

    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        raise gui.RedirectException(str(redirect_url))

    current_workspace = get_current_workspace(request.user, request.session)
    search_filters = SearchFilters(
        workspace=get_filter_value_from_workspace(current_workspace)
    )
    raise gui.RedirectException(
        get_app_route_url(
            explore_page, query_params=search_filters.model_dump(exclude_defaults=True)
        )
    )


@gui.route(app, "/account/saved")
def saved_route(request: Request):
    with account_page_wrapper(request, AccountTabs.saved):
        all_saved_runs_tab(request)
    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url,
            canonical_url=url,
            title="Saved • Gooey.AI",
            description="Your saved runs.",
            robots="noindex,nofollow",
        )
    )


@gui.route(app, "/account/api-keys/")
def api_keys_route(request: Request):
    with account_page_wrapper(request, AccountTabs.api_keys):
        api_keys_tab(request)
    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url,
            canonical_url=url,
            title="API Keys • Gooey.AI",
            description="Your API keys.",
            robots="noindex,nofollow",
        )
    )


@gui.route(app, "/workspaces/members/")
def members_route(request: Request):
    with account_page_wrapper(request, AccountTabs.members) as current_workspace:
        if current_workspace.is_personal:
            raise gui.RedirectException(get_route_path(profile_route))
        workspaces_page(request.user, request.session)

    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url,
            canonical_url=url,
            title="Members • Gooey.AI",
            description="Your teams.",
            robots="noindex,nofollow",
        )
    )


@gui.route(app, "/workspaces/{workspace_slug}/invite/{email}-{invite_id}")
def invitation_route(
    request: Request,
    invite_id: str,
    workspace_slug: str | None,
    email: str | None,
):
    invite = load_invite_from_hashid_or_404(invite_id)
    invitation_page(current_user=request.user, session=request.session, invite=invite)

    description = invite.created_by.full_name()
    if email := invite.created_by.email:
        description += f" ({email})"
    elif phone := invite.created_by.phone_number:
        description += f" ({phone.as_international})"
    description += f" invited you to join {invite.workspace.display_name()} on Gooey.AI"

    return dict(
        meta=raw_build_meta_tags(
            url=str(request.url),
            title=invite.workspace.display_name(),
            description=description,
            image=invite.workspace.get_photo(),
            robots="noindex,nofollow",
        )
    )


def load_invite_from_hashid_or_404(invite_id: str) -> WorkspaceInvite:
    try:
        invite_id = WorkspaceInvite.api_hashids.decode(invite_id)[0]
        return WorkspaceInvite.objects.select_related("workspace").get(id=invite_id)
    except (IndexError, WorkspaceInvite.DoesNotExist):
        raise HTTPException(status_code=404)


class TabData(typing.NamedTuple):
    title: str
    route: typing.Callable


class AccountTabs(TabData, Enum):
    profile = TabData(title=f"{icons.profile} Profile", route=profile_route)
    members = TabData(title=f"{icons.company} Members", route=members_route)
    saved = TabData(title=f"{icons.save} Saved", route=saved_route)
    api_keys = TabData(title=f"{icons.api} API Keys", route=api_keys_route)
    billing = TabData(title=f"{icons.billing} Billing", route=account_route)

    @property
    def url_path(self) -> str:
        return get_route_path(self.route)

    @classmethod
    def get_tabs_for_user(
        cls, user: typing.Optional["AppUser"], workspace: Workspace | None
    ) -> list["AccountTabs"]:
        ret = list(cls)

        if workspace.is_personal:
            ret.remove(cls.members)
        else:
            ret.remove(cls.profile)
            if not workspace.memberships.get(user=user).can_edit_workspace():
                ret.remove(cls.billing)

        return ret


def billing_tab(request: Request, workspace: Workspace):
    if not workspace.memberships.get(user=request.user).can_edit_workspace():
        raise gui.RedirectException(get_route_path(members_route))
    return billing_page(workspace=workspace, user=request.user, session=request.session)


def profile_tab(request: Request, workspace: Workspace):
    return edit_user_profile_page(workspace=workspace)


def all_saved_runs_tab(request: Request):
    workspace = get_current_workspace(request.user, request.session)
    pr_filter = Q(workspace=workspace)
    if workspace.is_personal:
        pr_filter |= Q(created_by=request.user, workspace__isnull=True)
    else:
        pr_filter &= (
            ~Q(workspace_access=WorkflowAccessLevel.VIEW_ONLY)
            | Q(created_by=request.user)
            | ~Q(public_access=WorkflowAccessLevel.VIEW_ONLY)
        )

    qs = PublishedRun.objects.select_related(
        "workspace", "created_by", "saved_run"
    ).filter(pr_filter)

    prs, cursor = paginate_queryset(
        qs=qs, ordering=["-updated_at"], cursor=request.query_params
    )

    gui.write("# Saved Workflows")
    explore_path = get_route_path(explore_page)

    if not prs:
        # empty state
        if workspace.is_personal:
            gui.caption(
                f"""
                You haven't saved any workflows yet. To get started, \
                [Explore our workflows]({explore_path}) and tap **Save** \
                to make one your own.
                """
            )
        else:
            gui.caption(
                f"""
                Your team hasn't shared any saved workflows yet. To get started, \
                [Explore our workflows]({explore_path}) and tap **Save** to \
                collaborate together.
                """
            )
        return

    if workspace.is_personal:
        if handle := workspace.handle:
            gui.caption(
                f"""
                All your Saved workflows are here, with public ones listed on your \
                profile page at {handle.get_app_url()}.
                """
            )
        else:
            edit_profile_url = AccountTabs.profile.url_path
            gui.caption(
                f"""
                All your Saved workflows are here. Public ones will be listed on \
                your profile page if you [create a username]({edit_profile_url}).
                """
            )
    else:
        workspace_name = workspace.display_name(request.user)
        gui.caption(
            f"Saved workflows of **{workspace_name}** are here and visible & editable by other workspace members."
        )

    def _render_run(pr: PublishedRun):
        workflow = Workflow(pr.workflow)
        render_saved_workflow_preview(
            workflow.page_cls,
            pr,
            workflow_pill=f"{workflow.emoji} {workflow.short_title}",
        )

    grid_layout(1, prs, _render_run)

    paginate_button(url=request.url, cursor=cursor)


def api_keys_tab(request: Request):
    workspace = get_current_workspace(request.user, request.session)

    gui.write("## 🔐 API Keys")
    manage_api_keys(workspace=workspace, user=request.user)

    gui.write("## 🛡 Secrets")
    manage_secrets_table(workspace, request.user)


@contextmanager
def account_page_wrapper(request: Request, current_tab: TabData):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        raise gui.RedirectException(str(redirect_url))

    with page_wrapper(request) as current_workspace:
        sidebar_logo_header()
        with gui.nav_tabs():
            for tab in AccountTabs.get_tabs_for_user(request.user, current_workspace):
                with gui.nav_item(tab.url_path, active=tab == current_tab):
                    gui.html(tab.title)

        with gui.nav_tab_content():
            yield current_workspace


def threaded_paypal_handle_subscription_updated(subscription_id: str) -> bool:
    """
    Always returns True when completed (for use in gui.run_in_thread())
    """
    try:
        subscription = paypal.Subscription.retrieve(subscription_id)
        PaypalWebhookHandler.handle_subscription_updated(subscription)
    except HTTPError:
        logger.exception(f"Unexpected PayPal error for sub: {subscription_id}")
        return False
    return True
