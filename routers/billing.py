import typing
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import quote_plus

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
    fastapi_request_body,
    fastapi_request_form,
    get_route_url,
)
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.profiles import edit_user_profile_page
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates
from gooey_ui.components.pills import pill
from payments.models import PricingPlan, Subscription
from routers.root import page_wrapper, get_og_url_path


USER_SUBSCRIPTION_METADATA_FIELD = "subscription_key"

app = APIRouter()


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
        return get_route_url(self.route)


def billing_tab(request: Request):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        return RedirectResponse(str(redirect_url))

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


@app.post("/__/stripe/create-checkout-session")
def create_checkout_session(
    request: Request, body_form: FormData = fastapi_request_form
):
    if not request.user:
        return RedirectResponse(
            request.url_for("login", query_params={"next": request.url.path})
        )

    lookup_key: str = body_form["lookup_key"]
    if (plan := PricingPlan.get_by_key(lookup_key)) and plan.stripe:
        line_item = plan.stripe.copy()
    else:
        return JSONResponse(
            {
                "message": "Invalid plan lookup key",
            }
        )

    if request.user.subscription and request.user.subscription.plan == plan.value:
        # already subscribed to the same plan
        return RedirectResponse("/", status_code=303)

    metadata = {USER_SUBSCRIPTION_METADATA_FIELD: lookup_key}

    checkout_session = stripe.checkout.Session.create(
        line_items=[line_item],
        mode="subscription",
        success_url=payment_processing_url,
        cancel_url=account_url,
        customer=request.user.get_or_create_stripe_customer(),
        metadata=metadata,
        subscription_data={"metadata": metadata},
        allow_promotion_codes=True,
        saved_payment_method_options={
            "payment_method_save": "enabled",
        },
    )

    return RedirectResponse(checkout_session.url, status_code=303)


@app.post("/__/stripe/create-portal-session")
def customer_portal(request: Request):
    customer = request.user.get_or_create_stripe_customer()
    portal_session = stripe.billing_portal.Session.create(
        customer=customer,
        return_url=account_url,
    )
    return RedirectResponse(portal_session.url, status_code=303)


@app.post(settings.PAYMENT_PROCESSING_PAGE_PATH)
@st.route
def payment_processing(request: Request):
    with page_wrapper(request):
        context = {
            "request": request,
            "settings": settings,
            "redirect_url": account_url,
        }
        st.html(templates.get_template("payment_processing.html").render(**context))
    return dict(
        meta=raw_build_meta_tags(url=str(request.url), title="Processing Payment...")
    )


payment_processing_url = str(
    furl(settings.APP_BASE_URL) / app.url_path_for(payment_processing.__name__)
)
account_url = str(
    furl(settings.APP_BASE_URL) / app.url_path_for(account_route.__name__)
)


@app.get("/__/billing/change-payment-method")
def change_payment_method(request: Request):
    if not request.user or not request.user.subscription:
        return RedirectResponse(account_url)

    match request.user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            session = stripe.checkout.Session.create(
                mode="setup",
                currency="usd",
                customer=request.user.get_or_create_stripe_customer(),
                setup_intent_data={
                    "metadata": {
                        "subscription_id": request.user.subscription.external_id,
                        "op": "change_payment_method",
                    },
                },
                success_url=payment_processing_url,
                cancel_url=account_url,
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
        return RedirectResponse(account_url, status_code=303)

    lookup_key = form_data["lookup_key"]
    new_plan = PricingPlan.get_by_key(lookup_key)
    if not new_plan:
        return JSONResponse(
            {
                "message": "Invalid plan lookup key",
            },
            status_code=400,
        )

    current_plan = PricingPlan(request.user.subscription.plan)

    if new_plan == current_plan:
        return RedirectResponse(account_url, status_code=303)

    if new_plan == PricingPlan.STARTER:
        request.user.subscription.cancel()
        request.user.subscription.delete()
        return RedirectResponse(payment_processing_url, status_code=303)

    match request.user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            if not new_plan.stripe:
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
                    new_plan.stripe.copy(),
                ],
                metadata={USER_SUBSCRIPTION_METADATA_FIELD: new_plan.key},
            )
            return RedirectResponse(payment_processing_url, status_code=303)
        case PaymentProvider.PAYPAL:
            if not new_plan.paypal:
                return JSONResponse(
                    {
                        "message": f"Paypal subscription not available for {new_plan}",
                    },
                    status_code=400,
                )

            subscription = paypal.Subscription.retrieve(
                request.user.subscription.external_id
            )
            approval_url = subscription.update_plan(
                plan_id=new_plan.paypal["plan_id"], plan=new_plan.paypal.get("plan", {})
            )
            return RedirectResponse(approval_url, status_code=303)
        case _:
            return JSONResponse(
                {
                    "message": "Not implemented for this payment provider",
                },
                status_code=400,
            )


@app.post("/__/stripe/webhook")
def webhook_received(request: Request, payload: bytes = fastapi_request_body):
    # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=request.headers["stripe-signature"],
        secret=settings.STRIPE_ENDPOINT_SECRET,
    )

    data = event.data.object

    customer = stripe.Customer.retrieve(data.customer)
    try:
        uid = customer.metadata.uid
    except AttributeError:
        uid = None
    if not uid:
        return JSONResponse(
            {
                "status": "failed",
                "error": "customer.metadata.uid not found",
            },
            status_code=400,
        )

    # Get the type of webhook event sent - used to check the status of PaymentIntents.
    match event["type"]:
        case "invoice.paid":
            _handle_invoice_paid(uid, data)
        case "checkout.session.completed":
            _handle_checkout_session_completed(uid, data)
        case "customer.subscription.created" | "customer.subscription.updated":
            _handle_subscription_updated(uid, data)
        case "customer.subscription.deleted":
            _handle_subscription_cancelled(uid, data)

    return JSONResponse({"status": "success"})


def _handle_invoice_paid(uid: str, invoice_data):
    invoice_id = invoice_data.id
    line_items = stripe.Invoice._static_request(
        "get",
        "/v1/invoices/{invoice}/lines".format(invoice=quote_plus(invoice_id)),
    )
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    user.add_balance(
        payment_provider=PaymentProvider.STRIPE,
        invoice_id=invoice_id,
        amount=line_items.data[0].quantity,
        charged_amount=line_items.data[0].amount,
    )
    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])
    if (
        user.subscription
        and user.subscription.should_send_monthly_spending_notification()
    ):
        send_monthly_spending_notification_email(user)


def _handle_checkout_session_completed(uid: str, session_data):
    setup_intent_id = session_data.get("setup_intent")
    if not setup_intent_id:
        # not a setup mode checkout
        return

    # set default payment method
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
    subscription_id = setup_intent.metadata.get("subscription_id")
    if not (
        user.subscription.payment_provider == PaymentProvider.STRIPE
        and user.subscription.external_id == subscription_id
    ):
        logger.error(f"Subscription {subscription_id} not found for user {user}")
        return

    stripe.Subscription.modify(
        subscription_id, default_payment_method=setup_intent.payment_method
    )


@transaction.atomic
def _handle_subscription_updated(uid: str, subscription_data):
    logger.info("Subscription updated")

    product = stripe.Product.retrieve(subscription_data.plan.product)
    plan = PricingPlan.get_by_stripe_product(product)
    if not plan:
        raise Exception(
            f"PricingPlan not found for product {subscription_data.plan.product}"
        )

    if subscription_data.get("status") != "active":
        logger.warning(f"Subscription {subscription_data.id} is not active")
        return

    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    if user.subscription and (
        user.subscription.payment_provider != PaymentProvider.STRIPE
        or user.subscription.external_id != subscription_data.id
    ):
        logger.warning(
            f"User {user} has different existing subscription {user.subscription}. Cancelling that..."
        )
        user.subscription.cancel()
        user.subscription.delete()
    elif not user.subscription:
        user.subscription = Subscription()

    user.subscription.plan = plan.value
    user.subscription.payment_provider = PaymentProvider.STRIPE
    user.subscription.external_id = subscription_data.id

    user.subscription.full_clean()
    user.subscription.save()
    user.save(update_fields=["subscription"])


def _handle_subscription_cancelled(uid: str, subscription_data):
    subscription = Subscription.objects.get_by_stripe_subscription_id(
        subscription_data.id
    )
    logger.info(f"Subscription {subscription} cancelled. Deleting it...")
    subscription.delete()


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
            account_url=account_url,
        ),
    )

    user.subscription.monthly_spending_notification_sent_at = datetime.now(
        tz=timezone.utc
    )
    user.subscription.save(update_fields=["monthly_spending_notification_sent_at"])
