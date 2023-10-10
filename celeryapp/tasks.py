import traceback
import typing
from time import time
from types import SimpleNamespace

import sentry_sdk

import gooey_ui as st
from app_users.models import AppUser
from bots.models import SavedRun
from celeryapp.celeryconfig import app
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import settings
from daras_ai_v2.base import StateKeys, err_msg_for_exc, BasePage
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates
from gooey_ui.pubsub import realtime_push
from gooey_ui.state import set_query_params


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

    st.set_session_state(state)
    run_time = 0
    yield_val = None
    error_msg = None
    set_query_params(query_params or {})

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
                yield_val = next(gen)
                # increment total time taken after every iteration
                run_time += time() - start_time
                continue
            # run completed
            except StopIteration:
                run_time += time() - start_time
                sr.price = page.deduct_credits(st.session_state)
                break
            # render errors nicely
            except Exception as e:
                run_time += time() - start_time
                traceback.print_exc()
                sentry_sdk.capture_exception(e)
                error_msg = err_msg_for_exc(e)
                break
            finally:
                save()
    finally:
        save(done=True)
        if not is_api_call:
            send_email_on_completion(page, sr)


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
