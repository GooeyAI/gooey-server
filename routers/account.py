import typing
from contextlib import contextmanager
from enum import Enum

import gooey_gui as gui
from django.db.models import Q
from fastapi.requests import Request
from furl import furl
from gooey_gui.core import RedirectException
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
from routers.root import page_wrapper, get_og_url_path
from workspaces.models import WorkspaceInvite
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


@gui.route(app, "/account/")
def account_route(request: Request):
    with account_page_wrapper(request, AccountTabs.billing):
        billing_tab(request)
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
    with account_page_wrapper(request, AccountTabs.profile):
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


@gui.route(app, "/saved/")
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


@gui.route(app, "/workspaces/")
def workspaces_route(request: Request):
    with account_page_wrapper(request, AccountTabs.workspaces):
        workspaces_page(request.user, request.session)

    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url,
            canonical_url=url,
            title="Teams • Gooey.AI",
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
    from routers.root import login

    if not request.user or request.user.is_anonymous:
        next_url = request.url.path
        redirect_url = str(furl(get_route_path(login), query_params={"next": next_url}))
        raise RedirectException(redirect_url)

    try:
        invite_id = WorkspaceInvite.api_hashids.decode(invite_id)[0]
        invite = WorkspaceInvite.objects.get(id=invite_id)
    except (IndexError, WorkspaceInvite.DoesNotExist):
        return Response(status_code=404)

    with page_wrapper(request):
        invitation_page(
            current_user=request.user, session=request.session, invite=invite
        )

    return dict(
        meta=raw_build_meta_tags(
            url=str(request.url),
            title=f"Join {invite.workspace.display_name()} • Gooey.AI",
            description=f"Invitation to join {invite.workspace.display_name()}",
            robots="noindex,nofollow",
        )
    )


class TabData(typing.NamedTuple):
    title: str
    route: typing.Callable


class AccountTabs(TabData, Enum):
    billing = TabData(title=f"{icons.billing} Billing", route=account_route)
    profile = TabData(title=f"{icons.profile} Profile", route=profile_route)
    saved = TabData(title=f"{icons.save} Saved", route=saved_route)
    api_keys = TabData(title=f"{icons.api} API Keys", route=api_keys_route)
    workspaces = TabData(title=f"{icons.company} Teams", route=workspaces_route)

    @property
    def url_path(self) -> str:
        return get_route_path(self.route)

    @classmethod
    def get_tabs_for_user(cls, user: AppUser | None) -> list["AccountTabs"]:
        from daras_ai_v2.base import BasePage

        ret = list(cls)
        if not BasePage.is_user_admin(user):
            ret.remove(cls.workspaces)

        return ret


def billing_tab(request: Request):
    workspace = get_current_workspace(request.user, request.session)
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

    if prs:
        if request.user.handle:
            gui.caption(
                "All your Saved workflows are here, with public ones listed on your "
                f"profile page at {request.user.handle.get_app_url()}."
            )
        else:
            edit_profile_url = AccountTabs.profile.url_path
            gui.caption(
                "All your Saved workflows are here. Public ones will be listed on your "
                f"profile page if you [create a username]({edit_profile_url})."
            )

        with gui.div(className="mt-4"):
            grid_layout(3, prs, _render_run)
    else:
        gui.write("No saved runs yet", className="text-muted")


def api_keys_tab(request: Request):
    gui.write("# 🔐 API Keys")
    manage_api_keys(request.user)


@contextmanager
def account_page_wrapper(request: Request, current_tab: TabData):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        raise gui.RedirectException(str(redirect_url))

    with page_wrapper(request):
        gui.div(className="mt-5")
        with gui.nav_tabs():
            for tab in AccountTabs.get_tabs_for_user(request.user):
                with gui.nav_item(tab.url_path, active=tab == current_tab):
                    gui.html(tab.title)

        with gui.nav_tab_content():
            yield


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
