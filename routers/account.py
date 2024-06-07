import typing
from contextlib import contextmanager
from enum import Enum

from django.db import transaction
from fastapi import APIRouter
from fastapi.requests import Request
from furl import furl
from loguru import logger

import gooey_ui as st
from app_users.models import AppUser, PaymentProvider
from bots.models import PublishedRun, PublishedRunVisibility, Workflow
from daras_ai_v2 import icons, paypal
from daras_ai_v2.base import RedirectException
from daras_ai_v2.billing import billing_page
from daras_ai_v2.fastapi_tricks import (
    get_route_path,
    get_route_url,
)
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.profiles import edit_user_profile_page
from gooey_ui.components.pills import pill
from payments.models import Subscription
from payments.plans import PricingPlan
from routers.root import page_wrapper, get_og_url_path

app = APIRouter()


@app.post("/payment-processing/")
@st.route
def payment_processing_route(
    request: Request, provider: str = None, subscription_id: str = None
):
    waiting_time_sec = 3
    subtext = None

    if provider == "paypal":
        if (sub_id := subscription_id) and st.run_in_thread(
            threaded_paypal_handle_subscription_updated, args=[sub_id]
        ):
            waiting_time_sec = 0
        else:
            waiting_time_sec = 30
            subtext = (
                "PayPal transactions take up to a minute to reflect in your account"
            )

    with page_wrapper(request, className="m-auto"):
        with st.center():
            with st.div(className="d-flex align-items-center"):
                st.div(
                    className="gooey-spinner me-4",
                    style=dict(height="3rem", width="3rem"),
                )
                st.write("# Processing payment...")
            st.caption(subtext)

    st.js(
        # language=JavaScript
        """
        setTimeout(() => {
            window.location.href = redirectUrl;
        }, waitingTimeMs);
        """,
        waitingTimeMs=waiting_time_sec * 1000,
        redirectUrl=(get_route_url(account_route)),
    )

    return dict(
        meta=raw_build_meta_tags(url=str(request.url), title="Processing Payment...")
    )


@app.post("/account/")
@st.route
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


@app.post("/account/profile/")
@st.route
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


@app.post("/saved/")
@st.route
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


@app.post("/account/api-keys/")
@st.route
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


class TabData(typing.NamedTuple):
    title: str
    route: typing.Callable


class AccountTabs(TabData, Enum):
    billing = TabData(title=f"{icons.billing} Billing", route=account_route)
    profile = TabData(title=f"{icons.profile} Profile", route=profile_route)
    saved = TabData(title=f"{icons.save} Saved", route=saved_route)
    api_keys = TabData(title=f"{icons.api} API Keys", route=api_keys_route)

    @property
    def url_path(self) -> str:
        return get_route_path(self.route)


def billing_tab(request: Request):
    return billing_page(request.user)


def profile_tab(request: Request):
    return edit_user_profile_page(user=request.user)


def all_saved_runs_tab(request: Request):
    prs = PublishedRun.objects.filter(
        created_by=request.user,
    ).order_by("-updated_at")

    def _render_run(pr: PublishedRun):
        workflow = Workflow(pr.workflow)
        visibility = PublishedRunVisibility(pr.visibility)

        with st.div(className="mb-2 d-flex justify-content-between align-items-start"):
            pill(
                visibility.get_badge_html(),
                unsafe_allow_html=True,
                className="border border-dark",
            )
            pill(workflow.short_title, className="border border-dark")

        workflow.page_cls().render_published_run_preview(pr)

    st.write("# Saved Workflows")

    if prs:
        if request.user.handle:
            st.caption(
                "All your Saved workflows are here, with public ones listed on your "
                f"profile page at {request.user.handle.get_app_url()}."
            )
        else:
            edit_profile_url = AccountTabs.profile.url_path
            st.caption(
                "All your Saved workflows are here. Public ones will be listed on your "
                f"profile page if you [create a username]({edit_profile_url})."
            )

        with st.div(className="mt-4"):
            grid_layout(3, prs, _render_run)
    else:
        st.write("No saved runs yet", className="text-muted")


def api_keys_tab(request: Request):
    st.write("# 🔐 API Keys")
    manage_api_keys(request.user)


@contextmanager
def account_page_wrapper(request: Request, current_tab: TabData):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        raise RedirectException(str(redirect_url))

    with page_wrapper(request):
        st.div(className="mt-5")
        with st.nav_tabs():
            for tab in AccountTabs:
                with st.nav_item(tab.url_path, active=tab == current_tab):
                    st.html(tab.title)

        with st.nav_tab_content():
            yield


def paypal_handle_subscription_updated(subscription: paypal.Subscription):
    logger.info("Subscription updated")

    plan = PricingPlan.get_by_paypal_plan_id(subscription.plan_id)
    if not plan:
        logger.error(f"Invalid plan ID: {subscription.plan_id}")
        return

    if not subscription.status == "ACTIVE":
        logger.warning(f"Subscription {subscription.id} is not active")
        return

    user = AppUser.objects.get(uid=subscription.custom_id)
    if user.subscription and (
        user.subscription.payment_provider != PaymentProvider.PAYPAL
        or user.subscription.external_id != subscription.id
    ):
        logger.warning(
            f"User {user} has different existing subscription {user.subscription}. Cancelling that..."
        )
        user.subscription.cancel()
        user.subscription.delete()
    elif not user.subscription:
        user.subscription = Subscription()

    user.subscription.plan = plan.db_value
    user.subscription.payment_provider = PaymentProvider.PAYPAL
    user.subscription.external_id = subscription.id

    user.subscription.full_clean()
    user.subscription.save()
    user.save(update_fields=["subscription"])


def threaded_paypal_handle_subscription_updated(subscription_id: str) -> bool:
    """
    Always returns True when completed (for use in st.run_in_thread())
    """
    subscription = paypal.Subscription.retrieve(subscription_id)
    paypal_handle_subscription_updated(subscription)
    return True
