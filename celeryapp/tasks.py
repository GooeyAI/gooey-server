import datetime
import html
import traceback
import typing
from time import time
from types import SimpleNamespace

import gooey_gui as gui
import requests
import sentry_sdk
from django.db.models import Sum
from django.utils import timezone
from fastapi import HTTPException
from loguru import logger

from app_users.models import AppUser, AppUserTransaction
from bots.admin_links import change_obj_url
from bots.models import SavedRun, Platform, Workflow
from celeryapp.celeryconfig import app
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import settings
from daras_ai_v2.base import StateKeys, BasePage
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.send_email import send_email_via_postmark, send_low_balance_email
from daras_ai_v2.settings import templates
from gooeysite.bg_db_conn import db_middleware
from payments.auto_recharge import (
    should_attempt_auto_recharge,
    run_auto_recharge_gracefully,
)

DEFAULT_RUN_STATUS = "Running..."


@app.task
def runner_task(
    *,
    page_cls: typing.Type[BasePage],
    user_id: int,
    run_id: str,
    uid: str,
    channel: str,
    unsaved_state: dict[str, typing.Any] = None,
) -> int:
    start_time = time()
    error_msg = None

    @db_middleware
    def save_on_step(yield_val: str | tuple[str, dict] = None, *, done: bool = False):
        if isinstance(yield_val, tuple):
            run_status, extra_output = yield_val
        else:
            run_status = yield_val
            extra_output = {}

        if done:
            run_status = None
        else:
            run_status = run_status or DEFAULT_RUN_STATUS

        output = (
            # extract status of the run
            {
                StateKeys.error_msg: error_msg,
                StateKeys.run_time: time() - start_time,
                StateKeys.run_status: run_status,
            }
            # extract outputs from local state
            | {
                k: v
                for k, v in gui.session_state.items()
                if k in page.ResponseModel.__fields__
            }
            # add extra outputs from the run
            | extra_output
        )

        # send outputs to ui
        gui.realtime_push(channel, output)
        # save to db
        page.dump_state_to_sr(gui.session_state | output, sr)

    user = AppUser.objects.get(id=user_id)
    page = page_cls(request=SimpleNamespace(user=user))
    page.setup_sentry()
    sr = page.run_doc_sr(run_id, uid)
    gui.set_session_state(sr.to_dict() | (unsaved_state or {}))
    gui.set_query_params(dict(run_id=run_id, uid=uid))

    try:
        save_on_step()
        for val in page.main(sr, gui.session_state):
            save_on_step(val)

    # render errors nicely
    except Exception as e:
        if isinstance(e, UserError):
            sentry_level = e.sentry_level
            logger.warning(e)
        else:
            sentry_level = "error"
            traceback.print_exc()
        sentry_sdk.capture_exception(e, level=sentry_level)
        error_msg = err_msg_for_exc(e)
        sr.error_type = type(e).__qualname__
        sr.error_code = getattr(e, "status_code", None)

    # run completed successfully, deduct credits
    else:
        sr.transaction, sr.price = page.deduct_credits(gui.session_state)

    # save everything, mark run as completed
    finally:
        save_on_step(done=True)

    return sr.id


@app.task
def post_runner_tasks(saved_run_id: int):
    sr = SavedRun.objects.get(id=saved_run_id)
    user = AppUser.objects.get(uid=sr.uid)

    if not sr.is_api_call:
        send_email_on_completion(sr)

    if should_attempt_auto_recharge(user):
        run_auto_recharge_gracefully(user)

    run_low_balance_email_check(user)


def err_msg_for_exc(e: Exception):
    if isinstance(e, UserError):
        return e.message
    elif isinstance(e, HTTPException):
        return f"(HTTP {e.status_code}) {e.detail})"
    elif isinstance(e, requests.HTTPError):
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
    else:
        return f"{type(e).__name__}: {e}"


def run_low_balance_email_check(user: AppUser):
    # don't send email if feature is disabled
    if not settings.LOW_BALANCE_EMAIL_ENABLED:
        return
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


def send_email_on_completion(sr: SavedRun):
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

    workflow = Workflow(sr.workflow)
    page_cls = workflow.page_cls
    prompt = (page_cls.preview_input(sr.state) or "").strip().replace("\n", " ")
    recipe_title = page_cls.get_recipe_title()

    subject = (
        f"🌻 “{truncate_text_words(prompt, maxlen=50) or 'Run'}” {recipe_title} is done"
    )

    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=to_address,
        subject=subject,
        html_body=templates.get_template("run_complete_email.html").render(
            run_time_sec=round(run_time_sec),
            app_url=sr.get_app_url(),
            prompt=prompt,
            recipe_title=recipe_title,
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
