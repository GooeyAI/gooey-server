import datetime
import html
import traceback
import typing
from time import time
from types import SimpleNamespace

import requests
import sentry_sdk
from django.db.models import Sum
from django.utils import timezone
from fastapi import HTTPException

import gooey_ui as st
from app_users.models import AppUser, AppUserTransaction
from bots.admin_links import change_obj_url
from bots.models import SavedRun, Platform
from celeryapp.celeryconfig import app
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import settings
from daras_ai_v2.base import StateKeys, BasePage
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.send_email import send_email_via_postmark, send_low_balance_email
from daras_ai_v2.settings import templates
from gooey_ui.pubsub import realtime_push
from gooey_ui.state import set_query_params
from gooeysite.bg_db_conn import db_middleware, next_db_safe
from payments.tasks import run_auto_recharge_async


@app.task
def gui_runner(
    *,
    page_cls: typing.Type[BasePage],
    user_id: str,
    run_id: str,
    uid: str,
    state: dict,
    channel: str,
    query_params: dict = None,
    is_api_call: bool = False,
):
    page = page_cls(request=SimpleNamespace(user=AppUser.objects.get(id=user_id)))

    def event_processor(event, hint):
        event["request"] = {
            "method": "POST",
            "url": page.app_url(query_params=query_params),
            "data": state,
        }
        return event

    page.setup_sentry(event_processor=event_processor)

    sr = page.run_doc_sr(run_id, uid)
    sr.is_api_call = is_api_call

    st.set_session_state(state)
    run_time = 0
    yield_val = None
    error_msg = None
    set_query_params(query_params or {})

    @db_middleware
    def save(done=False):
        if done:
            # clear run status
            run_status = None
        else:
            # set run status to the yield value of generator
            run_status = yield_val or "Running..."
        if isinstance(run_status, tuple):
            run_status, extra_output = run_status
        else:
            extra_output = {}
        # set run status and run time
        status = {
            StateKeys.run_time: run_time,
            StateKeys.error_msg: error_msg,
            StateKeys.run_status: run_status,
        }
        output = (
            status
            |
            # extract outputs from local state
            {
                k: v
                for k, v in st.session_state.items()
                if k in page.ResponseModel.__fields__
            }
            | extra_output
        )
        # send outputs to ui
        realtime_push(channel, output)
        # save to db
        page.dump_state_to_sr(st.session_state | output, sr)

    try:
        gen = page.run_with_auto_recharge(st.session_state)
        save()
        while True:
            # record time
            start_time = time()
            try:
                # advance the generator (to further progress of run_with_auto_recharge())
                yield_val = next_db_safe(gen)
                # increment total time taken after every iteration
                run_time += time() - start_time
                continue
            # run completed
            except StopIteration:
                run_time += time() - start_time
                sr.transaction, sr.price = page.deduct_credits(st.session_state)
                break
            # render errors nicely
            except Exception as e:
                run_time += time() - start_time

                if isinstance(e, HTTPException) and e.status_code == 402:
                    error_msg = page.generate_credit_error_message(
                        example_id=query_params.get("example_id"),
                        run_id=run_id,
                        uid=uid,
                    )
                    try:
                        raise UserError(error_msg) from e
                    except UserError as e:
                        sentry_sdk.capture_exception(e, level=e.sentry_level)
                        break

                if isinstance(e, UserError):
                    sentry_level = e.sentry_level
                else:
                    sentry_level = "error"
                    traceback.print_exc()
                sentry_sdk.capture_exception(e, level=sentry_level)
                error_msg = err_msg_for_exc(e)
                break
            finally:
                save()
    finally:
        save(done=True)
        if not is_api_call:
            send_email_on_completion(page, sr)

        run_low_balance_email_check(uid)
        run_auto_recharge_async.apply(kwargs={"uid": uid})


def err_msg_for_exc(e: Exception):
    if isinstance(e, requests.HTTPError):
        response: requests.Response = e.response
        try:
            err_body = response.json()
        except requests.JSONDecodeError:
            err_str = response.text
        else:
            if isinstance(err_body, dict):
                format_exc = err_body.get("format_exc")
                if format_exc:
                    print("⚡️ " + format_exc)
                err_type = err_body.get("type")
                err_str = err_body.get("str")
                if err_type and err_str:
                    return f"(GPU) {err_type}: {err_str}"
            err_str = str(err_body)
        return f"(HTTP {response.status_code}) {html.escape(err_str[:1000])}"
    elif isinstance(e, HTTPException):
        return f"(HTTP {e.status_code}) {e.detail})"
    elif isinstance(e, UserError):
        return e.message
    else:
        return f"{type(e).__name__}: {e}"


def run_low_balance_email_check(uid: str):
    # don't send email if feature is disabled
    if not settings.LOW_BALANCE_EMAIL_ENABLED:
        return
    user = AppUser.objects.get(uid=uid)
    # don't send email if user is not paying or has enough balance
    if not user.is_paying or user.balance > settings.LOW_BALANCE_EMAIL_CREDITS:
        return
    last_purchase = (
        AppUserTransaction.objects.filter(user=user, amount__gt=0)
        .order_by("-created_at")
        .first()
    )
    email_date_cutoff = timezone.now() - datetime.timedelta(
        days=settings.LOW_BALANCE_EMAIL_DAYS
    )
    # send email if user has not been sent email in last X days or last purchase was after last email sent
    if (
        # user has not been sent any email
        not user.low_balance_email_sent_at
        # user was sent email before X days
        or (user.low_balance_email_sent_at < email_date_cutoff)
        # user has made a purchase after last email sent
        or (last_purchase and last_purchase.created_at > user.low_balance_email_sent_at)
    ):
        # calculate total credits consumed in last X days
        total_credits_consumed = abs(
            AppUserTransaction.objects.filter(
                user=user, amount__lt=0, created_at__gte=email_date_cutoff
            ).aggregate(Sum("amount"))["amount__sum"]
            or 0
        )
        send_low_balance_email(user=user, total_credits_consumed=total_credits_consumed)
        user.low_balance_email_sent_at = timezone.now()
        user.save(update_fields=["low_balance_email_sent_at"])


def send_email_on_completion(page: BasePage, sr: SavedRun):
    run_time_sec = sr.run_time.total_seconds()
    if (
        run_time_sec <= settings.SEND_RUN_EMAIL_AFTER_SEC
        or not settings.POSTMARK_API_TOKEN  # make dev easier
    ):
        return
    to_address = (
        AppUser.objects.filter(uid=sr.uid).values_list("email", flat=True).first()
    )
    if not to_address:
        return
    prompt = (page.preview_input(sr.state) or "").strip()
    title = (sr.state.get("__title") or page.title).strip()
    subject = f"🌻 “{truncate_text_words(prompt, maxlen=50)}” {title} is done"
    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=to_address,
        subject=subject,
        html_body=templates.get_template("run_complete_email.html").render(
            run_time_sec=round(run_time_sec),
            app_url=sr.get_app_url(),
            prompt=prompt,
            title=title,
        ),
        message_stream="gooey-ai-workflows",
    )


@app.task
def send_integration_attempt_email(*, user_id: int, platform: Platform, run_url: str):
    user = AppUser.objects.get(id=user_id)
    html_body = templates.get_template("integration_attempt_email.html").render(
        user=user,
        account_url=(change_obj_url(user)),
        run_url=run_url,
        integration_type=platform.label,
    )
    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address="sales@gooey.ai",
        subject=f"{user.display_name} Attempted to Connect to {platform.label}",
        html_body=html_body,
    )
