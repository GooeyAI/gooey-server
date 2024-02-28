from fastapi import HTTPException
import html
import traceback
import typing
import datetime
from time import time
from types import SimpleNamespace

import requests
import sentry_sdk

import gooey_ui as st
from app_users.models import AppUser, AppUserTransaction
from bots.models import SavedRun
from celeryapp.celeryconfig import app
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import settings
from daras_ai_v2.base import StateKeys, BasePage
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates
from gooey_ui.pubsub import realtime_push
from gooey_ui.state import set_query_params
from gooeysite.bg_db_conn import db_middleware, next_db_safe
from daras_ai_v2.send_email import send_low_balance_email
from django.db.models import Sum
from django.utils import timezone


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
        sr.set(page.state_to_doc(st.session_state | output))

    try:
        gen = page.run(st.session_state)
        save()
        while True:
            # record time
            start_time = time()
            try:
                # advance the generator (to further progress of run())
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
        low_balance_email(sr)
        if not is_api_call:
            send_email_on_completion(page, sr)


def err_msg_for_exc(e: Exception):
    if isinstance(e, requests.HTTPError):
        response: requests.Response = e.response
        try:
            err_body = response.json()
        except requests.JSONDecodeError:
            err_str = response.text
        else:
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


def low_balance_email(sr: SavedRun):
    user = AppUser.objects.get(uid=sr.uid)
    last_positive_transaction = (
        AppUserTransaction.objects.filter(user=user, amount__gt=0)
        .order_by("-created_at")
        .first()
    )
    if last_positive_transaction:
        last_positive_transaction = last_positive_transaction.created_at
    else:
        last_positive_transaction = timezone.now() - datetime.timedelta(days=8)
    if (
        user.is_paying
        and user.balance < settings.EMAIL_CREDITS_THRESHOLD
        and settings.ALLOW_SENDING_CREDIT_EMAILS
        and (
            user.low_balance_email_sent_at == None
            or user.low_balance_email_sent_at
            < timezone.now() - datetime.timedelta(days=7)
            or last_positive_transaction > user.low_balance_email_sent_at
        )
    ):
        total_credits_consumed = (
            -1
            * AppUserTransaction.objects.filter(
                user=user,
                created_at__gte=timezone.now() - datetime.timedelta(days=7),
                amount__lt=0,
            ).aggregate(Sum("amount"))["amount__sum"]
        )
        send_low_balance_email(
            user=user,
            total_credits_consumed=total_credits_consumed,
        )
        user.low_balance_email_sent_at = timezone.now()
        user.save()


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
