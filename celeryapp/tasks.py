import traceback
import typing
from time import time
from types import SimpleNamespace

import sentry_sdk

import gooey_ui as st
from app_users.models import AppUser
from celeryapp.celeryconfig import app
from daras_ai_v2.base import StateKeys, err_msg_for_exc, BasePage
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
    example_id: str = None,
):
    self = page_cls(request=SimpleNamespace(user=AppUser.objects.get(id=user_id)))

    st.set_session_state(state)
    run_time = 0
    yield_val = None
    error_msg = None
    url = self.app_url(run_id=run_id, uid=uid)
    set_query_params(dict(run_id=run_id, uid=uid, example_id=example_id))

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
                if k in self.ResponseModel.__fields__
            }
            | extra_output
        )
        # send outputs to ui
        realtime_push(channel, output)
        # save to db
        self.run_doc_ref(run_id, uid).set(self.state_to_doc(st.session_state | output))

        print(f"{url} {status}")

    try:
        gen = self.run(st.session_state)
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
                self.deduct_credits(st.session_state)
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
