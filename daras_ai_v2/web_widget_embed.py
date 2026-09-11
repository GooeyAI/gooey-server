import datetime
from typing import Any, Iterator

import gooey_gui as gui
from bots.models import SavedRun
from bots.models.message_thread import MessageThread
from daras_ai_v2 import settings
from daras_ai_v2.csv_lines import csv_decode_row
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    format_chat_entry,
    get_entry_images,
    get_entry_text,
)
from daras_ai_v2.language_model_openai_audio import is_realtime_audio_url


def load_chat_widget_lib():
    gui.html(
        f'<script id="gooey-embed-script" src="{settings.WEB_WIDGET_LIB}"></script>'
    )


def build_chat_widget_input_request_body(
    sr: SavedRun,
    state: dict,
    input_data: dict,
) -> tuple[dict, MessageThread | None]:
    from daras_ai_v2.bots import handle_location_msg

    if input_data.get("edit_run_url"):
        return build_chat_widget_edit_request_body(input_data)

    ret = _copy_raw_inputs(input_data)
    messages = (state.get("messages") or []).copy()
    if messages:
        ret["messages"] = messages

    button_pressed: list[str] | None = input_data.get("button_pressed")
    if button_pressed:
        # encoded by parse_html
        target, title = None, None
        parts = csv_decode_row(button_pressed.get("button_id", ""))
        if len(parts) >= 3:
            target = parts[1]
            title = parts[-1]
        value = title or button_pressed.get("button_title", "")
        if target and target != "input_prompt":
            ret[target] = value
        else:
            ret["input_prompt"] = value

    input_location: dict[str, float] | None = input_data.get("input_location")
    if input_location:
        ret["input_prompt"] = handle_location_msg(input_location)

    prev_input = state.get("raw_input_text") or ""
    prev_input_images = state.get("input_images")
    prev_input_audio = state.get("input_audio")
    prev_input_documents = state.get("input_documents")
    prev_chat_input = (
        prev_input or prev_input_images or prev_input_audio or prev_input_documents
    )
    prev_output = (state.get("raw_output_text") or [""])[0]
    if prev_chat_input and prev_output:
        user_entry = format_chat_entry(
            role=CHATML_ROLE_USER,
            content_text=prev_input,
            input_images=prev_input_images,
            # input_audio=prev_input_audio,
            input_documents=prev_input_documents,
        )
        extra_content = user_extra_content(
            state, get_entry_text(user_entry), prev_input_audio, prev_input_documents
        )
        if extra_content:
            user_entry["extra_content"] = extra_content

        # a turn is produced by one run, and the assistant half is the half that
        # run answered with - so the run is recorded here, once, and the user
        # half is rendered from it rather than storing its own copy. The URL is
        # used internally; serializable run metadata lives in extra_content.
        assistant_entry = format_chat_entry(
            role=CHATML_ROLE_ASSISTANT,
            content_text=prev_output,
        ) | {"run_url": sr.get_app_url()}
        assistant_entry["extra_content"] = assistant_extra_content(
            sr, state, prev_output
        )

        # append previous input to the history
        ret["messages"] = messages + [user_entry, assistant_entry]

    any_prev_input = prev_chat_input or state.get("input_prompt")
    if any_prev_input and sr.message_thread and sr.message_thread.last_run_id == sr.id:
        message_thread = sr.message_thread
    else:
        message_thread = None

    return ret, message_thread


def build_chat_widget_edit_request_body(
    input_data: dict,
) -> tuple[dict, MessageThread | None]:
    """
    Re-run the turn that the run at `input_data["edit_run_url"]` produced. Like
    a normal turn, only the turn's inputs and history are sent - everything else
    is layered from the published run at submit time - rather than a snapshot of
    the edited run's whole state, which would pin a stale bot script and settings.

    No ownership check: editing never overwrites anything, it only creates a new
    run under the caller's uid from state that is already viewable by run url.
    The thread pointer it repoints is guarded by `_can_use_message_thread`.
    """
    from daras_ai_v2.workflow_url_input import url_to_runs

    sr = url_to_runs(input_data["edit_run_url"])[1]
    input_prompt = input_data.get("input_prompt")
    if input_prompt is None:
        # a re-run sends no prompt: the turn is asked again exactly as it was
        state = sr.state
    else:
        state = input_data
    ret = _copy_raw_inputs(state)
    ret["messages"] = (sr.state.get("messages") or []).copy()
    return ret, None


def _copy_raw_inputs(input_data: dict) -> dict[str, Any | None]:
    return {
        "input_prompt": input_data.get("input_prompt"),
        "input_audio": input_data.get("input_audio") or None,
        "input_images": input_data.get("input_images") or None,
        "input_documents": input_data.get("input_documents") or None,
    }


def user_extra_content(
    state: dict,
    raw_input_text: str,
    input_audio: str | None,
    input_documents: list[str] | None,
) -> dict[str, Any]:
    ret = {}
    input_prompt = state.get("input_prompt")
    if input_prompt is not None and input_prompt != raw_input_text:
        ret["display_content"] = input_prompt
    if input_audio:
        ret["audio"] = input_audio
    if input_documents:
        ret["documents"] = input_documents
    return ret


def assistant_extra_content(
    sr: SavedRun,
    state: dict,
    raw_output_text: str,
) -> dict[str, Any]:
    ret = {}
    output_text = (state.get("output_text") or [""])[0]
    if output_text and output_text != raw_output_text:
        ret["display_content"] = output_text
    output_video = state.get("output_video")
    if output_video:
        ret["video"] = output_video
    output_audio = state.get("output_audio")
    if output_audio:
        ret["audio"] = output_audio
    # isoformat because this is persisted into the run's json state
    ret["created_at"] = sr.created_at.isoformat()
    if sr.run_time:
        # named as the streaming api's final_response event names it, since
        # both report how long the same run took to answer
        ret["run_time_sec"] = sr.run_time.total_seconds()
    return ret


def get_chat_widget_messages(state: dict, web_url: str | None = None) -> list[Any]:
    from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys
    from daras_ai_v2.bots import parse_bot_html

    messages = []  # chat widget internal mishmash format
    input_audio = state.get("input_audio") or ""
    input_images = state.get("input_images") or []
    input_documents = state.get("input_documents") or []

    if is_realtime_audio_url(input_audio):
        entries = state.get("final_prompt", []).copy()
        input_audio = ""  # dont render ws audio url in chat widget
    else:
        entries = state.get("messages", []).copy()

    messages.extend(history_entries_to_widget_messages(entries))

    # add last input to history if present
    input_prompt = state.get("input_prompt") or ""

    if input_prompt or input_images or input_audio or input_documents:
        messages.append(
            dict(
                role=CHATML_ROLE_USER,
                input_prompt=input_prompt,
                input_images=input_images,
                input_audio=input_audio,
                input_documents=input_documents,
                web_url=web_url,
                # a datetime here: this one is only serialized for the wire,
                # where jsonable_encoder renders it as isoformat
                created_at=state.get(StateKeys.created_at),
            ),
        )

        # add last output
        raw_output_text = state.get("raw_output_text") or []
        output_text = state.get("output_text") or []
        output_video = state.get("output_video") or []
        output_audio = state.get("output_audio") or []
        text = output_text and output_text[0] or ""

        if text:
            buttons, text, thinking, disable_feedback = parse_bot_html(text)
            if thinking:
                thinking_duration = state.get("metrics", {}).get(
                    "thinking_duration_sec"
                )
                template = settings.templates.get_template("thinking_summary.html")
                context = dict(
                    text=text,
                    thinking=thinking,
                    thinking_duration=thinking_duration,
                )
                text = template.render(context)
        else:
            buttons = []

        status = run_status = BasePage.get_run_state(state)
        match run_status:
            case RecipeRunState.starting:
                event_type = "conversation_start"
            case RecipeRunState.running:
                event_type = "message_part"
            case RecipeRunState.failed:
                event_type = "final_response"
                status = RecipeRunState.completed.value
                error_msg = state.get(StateKeys.error_msg) or ""
                text += f'\n<code className="text-gooeyDanger font_14_400">{error_msg}</code>'
            case _:
                event_type = "final_response"
                status = "completed"

        # An unsettled run is always sent: starting/running has no output yet but its message is
        # what draws the widget's progress state, and failed carries the error text appended
        # above. A settled run with nothing to show is not sent - the builder clears every
        # ResponseModel field when it edits a workflow, since the old answer may no longer apply,
        # while input_prompt is a request field and survives. That pairing left the widget
        # rendering an empty assistant bubble under an input it had already answered.
        run_settled = run_status in (RecipeRunState.completed, RecipeRunState.standby)
        if text or output_video or output_audio or not run_settled:
            messages.append(
                dict(
                    role=CHATML_ROLE_ASSISTANT,
                    type=event_type,
                    status=status,
                    detail=state.get(StateKeys.run_status) or "",
                    # the run's created_at is when the question was asked; the
                    # answer arrived a run time later
                    created_at=finished_at(
                        state.get(StateKeys.created_at),
                        state.get(StateKeys.run_time),
                    ),
                    # absent until the run finishes, so nothing shows mid-answer
                    run_time_sec=state.get(StateKeys.run_time),
                    raw_output_text=raw_output_text,
                    output_text=[text],
                    text=text,
                    output_video=output_video,
                    output_audio=output_audio,
                    references=state.get("references") or [],
                    buttons=buttons,
                    final_prompt=state.get("final_prompt"),
                    web_url=web_url,
                )
            )
    return messages


def history_entries_to_widget_messages(entries: list[Any]) -> Iterator[Any]:
    for user_entry, assistant_entry in iter_user_assistant_pairs(entries):
        if user_entry:
            yield user_entry_to_widget_message(user_entry, assistant_entry)
        if assistant_entry:
            yield assistant_entry_to_widget_message(assistant_entry)


def iter_user_assistant_pairs(
    entries: list[Any],
) -> Iterator[tuple[dict | None, dict | None]]:
    # a turn is a user entry followed by the assistant entry that answered it.
    # a turn's run is recorded on the assistant half, and only the immediately
    # following half counts: a turn whose answer was never saved is yielded
    # alone rather than borrowing a later turn's run, or editing it would re-run
    # the wrong one. an assistant entry with no user half is also yielded alone.
    # every other role (system, ...) is dropped
    prev_user_entry = None
    for entry in entries:
        role = entry.get("role")
        if role == CHATML_ROLE_USER:
            if prev_user_entry:
                yield prev_user_entry, None
            prev_user_entry = entry
        elif role == CHATML_ROLE_ASSISTANT:
            yield prev_user_entry, entry
            prev_user_entry = None
    if prev_user_entry:
        yield prev_user_entry, None


def user_entry_to_widget_message(
    user_entry: dict, assistant_entry: dict | None
) -> dict:
    extra_content = user_entry.get("extra_content") or {}
    text = extra_content.get("display_content", get_entry_text(user_entry)) or ""
    msg = dict(
        role=CHATML_ROLE_USER,
        input_prompt=text,
        input_images=get_entry_images(user_entry) or [],
    )
    if assistant_entry:
        if run_url := assistant_entry.get("run_url"):
            # the widget only offers to edit a message it can point at a run
            msg["web_url"] = run_url
        assistant_extra_content = assistant_entry.get("extra_content") or {}
        if created_at := assistant_extra_content.get("created_at"):
            msg["created_at"] = created_at
    if audio := extra_content.get("audio"):
        msg["input_audio"] = audio
    if documents := extra_content.get("documents"):
        msg["input_documents"] = documents
    return msg


def assistant_entry_to_widget_message(assistant_entry: dict) -> dict:
    from daras_ai_v2.bots import parse_bot_html

    extra_content = assistant_entry.get("extra_content") or {}
    text = extra_content.get("display_content", get_entry_text(assistant_entry)) or ""
    text = parse_bot_html(text)[1]
    # buttons, text = parse_bot_html(text)[:2]
    msg = dict(
        role=CHATML_ROLE_ASSISTANT,
        type="final_response",
        status="completed",
        output_text=[text],
        buttons=[],
    )
    if run_url := assistant_entry.get("run_url"):
        msg["web_url"] = run_url
    if audio := extra_content.get("audio"):
        msg["output_audio"] = audio
    if video := extra_content.get("video"):
        msg["output_video"] = video
    run_time_sec = extra_content.get("run_time_sec")
    if created_at := extra_content.get("created_at"):
        msg["created_at"] = finished_at(created_at, run_time_sec)
    if run_time_sec:
        msg["run_time_sec"] = run_time_sec
    return msg


def finished_at(
    created_at: str | datetime.datetime | None, run_time_sec: float | None
) -> str | datetime.datetime | None:
    """
    When a run's answer arrived: its created_at (when the question was asked)
    plus how long it took. Unchanged while the run has no time yet.
    """
    if not created_at or not run_time_sec:
        return created_at
    if isinstance(created_at, str):
        created_at = datetime.datetime.fromisoformat(created_at)
    return (created_at + datetime.timedelta(seconds=run_time_sec)).isoformat()
