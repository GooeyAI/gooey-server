import datetime
import html
import threading
import traceback
import typing
from time import time

import gooey_gui as gui
import requests
import sentry_sdk
from django.db.models import Sum, F
from django.utils import timezone
from fastapi import HTTPException
from loguru import logger

from app_users.models import AppUser, AppUserTransaction
from bots.admin_links import change_obj_url
from bots.models import Platform, SavedRun, Workflow, PublishedRun
from celeryapp.celeryconfig import app
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import gcs_v2, settings
from daras_ai_v2.base import BasePage, StateKeys, STOPPING_STATE
from daras_ai_v2.exceptions import StopRequested, UserError, is_stop_requested
from daras_ai_v2.send_email import send_email_via_postmark, send_low_balance_email
from daras_ai_v2.settings import templates
from gooeysite.bg_db_conn import db_middleware
from payments.auto_recharge import (
    run_auto_recharge_gracefully,
    should_attempt_auto_recharge,
)
from workspaces.widgets import set_current_workspace

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace


DEFAULT_RUN_STATUS = "Running..."

threadlocal = threading.local()


def get_running_saved_run() -> SavedRun | None:
    try:
        return threadlocal.saved_run
    except AttributeError:
        return None


@app.task
def runner_task(
    *,
    page_cls: typing.Type[BasePage],
    user_id: int,
    run_id: str,
    uid: str,
    channel: str,
    unsaved_state: dict[str, typing.Any] | None = None,
    deduct_credits: bool = True,
):
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
        elif is_stop_requested():
            run_status = STOPPING_STATE
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
                if k in page.ResponseModel.model_fields
            }
            # add extra outputs from the run
            | extra_output
        )

        # send outputs to ui
        gui.realtime_push(channel, output)
        # dont save unsaved_state
        saved_state = gui.session_state | output
        if unsaved_state:
            for k in unsaved_state:
                saved_state.pop(k, None)
        # save to db
        page.dump_state_to_sr(saved_state, sr)

    page = page_cls(
        user=AppUser.objects.get(id=user_id),
        query_params=dict(run_id=run_id, uid=uid),
    )
    page.setup_sentry()
    sr = page.current_sr
    set_current_workspace(page.request.session, int(sr.workspace_id))
    threadlocal.saved_run = sr
    gui.set_session_state(sr.to_dict() | (unsaved_state or {}))

    if sr.parent_version:
        # Increment run count for parent published run
        PublishedRun.objects.filter(id=sr.parent_version.published_run_id).update(
            run_count=F("run_count") + 1
        )

    try:
        save_on_step()
        for val in page.main(sr, gui.session_state):
            save_on_step(val)

    # render errors nicely
    except Exception as e:
        if isinstance(e, UserError):
            sentry_level = e.sentry_level
            logger.warning("\n".join(map(str, [e, e.__cause__])))
        else:
            sentry_level = "error"
            traceback.print_exc()
        sentry_sdk.capture_exception(e, level=sentry_level)
        error_msg = err_msg_for_exc(e)
        sr.error_msg = error_msg
        sr.error_type = type(e).__qualname__
        sr.error_code = getattr(e, "status_code", None)

        if isinstance(e, StopRequested) and deduct_credits:
            sr.transaction, sr.price = page.deduct_credits(gui.session_state)

    # run completed successfully, deduct credits
    else:
        if deduct_credits:
            sr.transaction, sr.price = page.deduct_credits(gui.session_state)

    # save everything, mark run as completed
    finally:
        save_on_step(done=True)
        threadlocal.saved_run = None

    post_runner_tasks.delay(sr.id)


@app.task
def post_runner_tasks(saved_run_id: int):
    sr = SavedRun.objects.get(id=saved_run_id)

    if not sr.is_api_call:
        send_email_on_completion(sr)

    if should_attempt_auto_recharge(sr.workspace):
        run_auto_recharge_gracefully(sr.workspace)

    run_low_balance_email_check(sr.workspace)


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


def run_low_balance_email_check(workspace: "Workspace"):
    # don't send email if feature is disabled
    if not settings.LOW_BALANCE_EMAIL_ENABLED:
        return
    # don't send email if user is not paying or has enough balance
    if (
        not workspace.is_paying
        or workspace.balance > settings.LOW_BALANCE_EMAIL_CREDITS
    ):
        return
    last_purchase = (
        AppUserTransaction.objects.filter(workspace=workspace, amount__gt=0)
        .order_by("-created_at")
        .first()
    )
    email_date_cutoff = timezone.now() - datetime.timedelta(
        days=settings.LOW_BALANCE_EMAIL_DAYS
    )
    # send email if user has not been sent email in last X days or last purchase was after last email sent
    if (
        # user has not been sent any email
        not workspace.low_balance_email_sent_at
        # user was sent email before X days
        or (workspace.low_balance_email_sent_at < email_date_cutoff)
        # user has made a purchase after last email sent
        or (
            last_purchase
            and last_purchase.created_at > workspace.low_balance_email_sent_at
        )
    ):
        # calculate total credits consumed in last X days
        total_credits_consumed = abs(
            AppUserTransaction.objects.filter(
                workspace=workspace,
                amount__lt=0,
                created_at__gte=email_date_cutoff,
            ).aggregate(Sum("amount"))["amount__sum"]
            or 0
        )
        send_low_balance_email(
            workspace=workspace, total_credits_consumed=total_credits_consumed
        )
        workspace.low_balance_email_sent_at = timezone.now()
        workspace.save(update_fields=["low_balance_email_sent_at"])


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


@app.task
def update_gcs_content_types(urls: dict[str, str]) -> None:
    for url, content_type in urls.items():
        try:
            gcs_v2.update_content_type(url, content_type)
        except Exception as e:
            traceback.print_exc()
            sentry_sdk.capture_exception(e)
