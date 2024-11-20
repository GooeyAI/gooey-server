import typing
from contextlib import contextmanager
from enum import Enum

import gooey_gui as gui
from django.db.models import Q
from fastapi.requests import Request
from furl import furl
from loguru import logger
from requests.models import HTTPError
from starlette.responses import Response

from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunVisibility, Workflow
from daras_ai_v2 import icons, paypal
from daras_ai_v2.billing import billing_page
from daras_ai_v2.fastapi_tricks import get_route_path, get_app_route_url
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.profiles import edit_user_profile_page
from payments.webhooks import PaypalWebhookHandler
from routers.custom_api_router import CustomAPIRouter
from routers.root import explore_page, page_wrapper, get_og_url_path
from workspaces.models import Workspace, WorkspaceInvite
from workspaces.views import invitation_page, workspaces_page
from workspaces.widgets import get_current_workspace

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
            window.location.href = redirectUrl;
        }, waitingTimeMs);
        """,
        waitingTimeMs=waiting_time_sec * 1000,
        redirectUrl=get_app_route_url(account_route),
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
    with account_page_wrapper(request, AccountTabs.profile) as current_workspace:
        if not current_workspace.is_personal:
            raise gui.RedirectException(get_route_path(members_route))
        profile_tab(request)
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
def old_saved_route(request: Request):
    raise gui.RedirectException(get_route_path(saved_route))


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
    try:
        invite_id = WorkspaceInvite.api_hashids.decode(invite_id)[0]
        invite = WorkspaceInvite.objects.select_related("workspace").get(id=invite_id)
    except (IndexError, WorkspaceInvite.DoesNotExist):
        return Response(status_code=404)

    with page_wrapper(request, show_header=False, show_footer=False):
        invitation_page(
            current_user=request.user, session=request.session, invite=invite
        )

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
        cls, user: AppUser | None, workspace: Workspace | None
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
    return billing_page(workspace)


def profile_tab(request: Request):
    return edit_user_profile_page(user=request.user)


def all_saved_runs_tab(request: Request):
    workspace = get_current_workspace(request.user, request.session)
    pr_filter = Q(workspace=workspace)
    if workspace.is_personal:
        pr_filter |= Q(created_by=request.user, workspace__isnull=True)
    prs = PublishedRun.objects.filter(pr_filter).order_by("-updated_at")

    def _render_run(pr: PublishedRun):
        workflow = Workflow(pr.workflow)
        visibility = PublishedRunVisibility(pr.visibility)

        with gui.div(className="mb-2 d-flex justify-content-between align-items-start"):
            gui.pill(
                visibility.get_badge_html(),
                unsafe_allow_html=True,
                className="border border-dark",
            )
            gui.pill(workflow.short_title, className="border border-dark")

        workflow.page_cls().render_published_run_preview(pr)

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
        if request.user.handle:
            edit_profile_url = AccountTabs.profile.url_path
            gui.caption(
                f"""
                All your Saved workflows are here. Public ones will be listed on \
                your profile page if you [create a username]({edit_profile_url}).
                """
            )
        else:
            gui.caption(
                f"""
                All your Saved workflows are here, with public ones listed on your \
                profile page at {request.user.handle.get_app_url()}.
                """
            )
    else:
        workspace_name = workspace.display_name(request.user)
        gui.caption(
            f"Saved workflows of **{workspace_name}** are here and visible & editable by other workspace members."
        )

    with gui.div(className="mt-4"):
        grid_layout(3, prs, _render_run)


def api_keys_tab(request: Request):
    gui.write("# 🔐 API Keys")
    workspace = get_current_workspace(request.user, request.session)
    manage_api_keys(workspace=workspace, user=request.user)


@contextmanager
def account_page_wrapper(request: Request, current_tab: TabData):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        raise gui.RedirectException(str(redirect_url))

    with page_wrapper(request) as current_workspace:
        gui.div(className="mt-5")
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
