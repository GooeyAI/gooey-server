import typing
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum

import stripe
from django.db import transaction
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, JSONResponse
from furl import furl
from loguru import logger
from starlette.datastructures import FormData

import gooey_ui as st
from app_users.models import AppUser, PaymentProvider
from bots.models import PublishedRun, PublishedRunVisibility, Workflow
from daras_ai_v2 import icons, paypal, settings
from daras_ai_v2.base import RedirectException
from daras_ai_v2.billing import billing_page
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_form,
    get_route_path,
    get_route_url,
)
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.profiles import edit_user_profile_page
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates
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
    subtext = None
    waiting_time_sec = 3

    if provider == "paypal":
        if sub_id := subscription_id:
            sub = paypal.Subscription.retrieve(sub_id)
            paypal_handle_subscription_updated(sub)
        else:
            subtext = (
                "PayPal transactions take up to a minute to reflect in your account"
            )
            waiting_time_sec = 30

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


@app.get("/__/billing/change-payment-method")
def change_payment_method(request: Request):
    if not request.user or not request.user.subscription:
        return RedirectResponse(get_route_url(account_route))

    match request.user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            session = stripe.checkout.Session.create(
                mode="setup",
                currency="usd",
                customer=request.user.get_or_create_stripe_customer(),
                setup_intent_data={
                    "metadata": {
                        "subscription_id": request.user.subscription.external_id,
                    },
                },
                success_url=get_route_url(payment_processing_route),
                cancel_url=get_route_url(account_route),
            )
            return RedirectResponse(session.url, status_code=303)
        case _:
            return JSONResponse(
                {
                    "message": "Not implemented for this payment provider",
                },
                status_code=400,
            )


@app.post("/__/billing/change-subscription")
def change_subscription(request: Request, form_data: FormData = fastapi_request_form):
    if not request.user:
        return RedirectResponse(get_route_url(account_route), status_code=303)

    lookup_key = form_data["lookup_key"]
    new_plan = PricingPlan.get_by_key(lookup_key)
    if not new_plan:
        return JSONResponse(
            {
                "message": "Invalid plan lookup key",
            },
            status_code=400,
        )

    current_plan = PricingPlan.from_sub(request.user.subscription)

    if new_plan == current_plan:
        return RedirectResponse(get_route_url(account_route), status_code=303)

    if new_plan == PricingPlan.STARTER:
        request.user.subscription.cancel()
        request.user.subscription.delete()
        return RedirectResponse(
            get_route_url(payment_processing_route), status_code=303
        )

    match request.user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            if not new_plan.monthly_charge:
                return JSONResponse(
                    {
                        "message": f"Stripe subscription not available for {new_plan}",
                    },
                    status_code=400,
                )

            subscription = stripe.Subscription.retrieve(
                request.user.subscription.external_id
            )
            stripe.Subscription.modify(
                subscription.id,
                items=[
                    {"id": subscription["items"].data[0], "deleted": True},
                    new_plan.get_stripe_line_item(),
                ],
                metadata={
                    settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: new_plan.key,
                },
            )
            return RedirectResponse(
                get_route_url(payment_processing_route), status_code=303
            )

        case PaymentProvider.PAYPAL:
            if not new_plan.monthly_charge:
                return JSONResponse(
                    {
                        "message": f"Paypal subscription not available for {new_plan}",
                    },
                    status_code=400,
                )

            subscription = paypal.Subscription.retrieve(
                request.user.subscription.external_id
            )
            paypal_plan_info = new_plan.get_paypal_plan()
            approval_url = subscription.update_plan(
                plan_id=paypal_plan_info["plan_id"],
                plan=paypal_plan_info["plan"],
            )
            return RedirectResponse(approval_url, status_code=303)
        case _:
            return JSONResponse(
                {
                    "message": "Not implemented for this payment provider",
                },
                status_code=400,
            )


@transaction.atomic
def send_monthly_spending_notification_email(user: AppUser):
    assert (
        user.subscription and user.subscription.monthly_spending_notification_threshold
    )

    if not user.email:
        logger.error(f"User doesn't have an email: {user=}")
        return

    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email,
        subject=f"[Gooey.AI] Monthly spending has exceeded ${user.subscription.monthly_spending_notification_threshold}",
        html_body=templates.get_template(
            "monthly_spending_notification_threshold_email.html"
        ).render(
            user=user,
            account_url=get_route_url(account_route),
        ),
    )

    user.subscription.monthly_spending_notification_sent_at = datetime.now(
        tz=timezone.utc
    )
    user.subscription.save(update_fields=["monthly_spending_notification_sent_at"])


@transaction.atomic
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
