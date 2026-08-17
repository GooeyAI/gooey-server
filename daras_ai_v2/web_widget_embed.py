import copy
from typing import Any, Iterator

import gooey_gui as gui
import yarl
from bots.models import SavedRun
from bots.models.message_thread import MessageThread
from daras_ai_v2 import settings
from daras_ai_v2.csv_lines import csv_decode_row
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    format_chat_entry,
    get_entry_images,
    get_entry_text,
)
from daras_ai_v2.language_model_openai_audio import is_realtime_audio_url
from daras_ai_v2.query_params_util import extract_query_params


def load_chat_widget_lib():
    gui.html(
        f'<script id="gooey-embed-script" src="{settings.WEB_WIDGET_LIB}"></script>'
    )


def chat_widget_input_to_request_body(
    sr: SavedRun,
    state: dict,
    input_data: dict,
    *,
    edit_sr: SavedRun | None = None,
) -> tuple[dict, MessageThread | None]:
    from daras_ai_v2.bots import handle_location_msg

    if edit_sr:
        request_body = _build_chat_widget_edit_request_body(
            current_sr=sr,
            state=state,
            edit_sr=edit_sr,
            input_prompt=input_data.get("input_prompt"),
        )
        # keep the conversation's own thread: create_new_run repoints last_run at
        # the replacement, so the sidebar row moves rather than forking a new one
        return request_body, edit_sr.message_thread

    ret = {
        "input_prompt": input_data.get("input_prompt"),
        "input_audio": input_data.get("input_audio") or None,
        "input_images": input_data.get("input_images") or None,
        "input_documents": input_data.get("input_documents") or None,
    }

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
        # both halves of a turn come from the same run, so they share its url.
        # the widget uses it to render a run link, and to edit that turn.
        run_url = sr.get_app_url()

        user_entry = format_chat_entry(
            role=CHATML_ROLE_USER,
            content_text=prev_input,
            input_images=prev_input_images,
            # input_audio=prev_input_audio,
            input_documents=prev_input_documents,
        ) | {
            "run_url": run_url,
            # isoformat because this is persisted into the run's json state.
            # only outgoing messages render a timestamp, so the assistant half
            # of the turn doesn't carry one
            "created_at": sr.created_at.isoformat(),
        }
        extra_content = user_extra_content(
            state, get_entry_text(user_entry), prev_input_audio, prev_input_documents
        )
        if extra_content:
            user_entry["extra_content"] = extra_content

        assistant_entry = format_chat_entry(
            role=CHATML_ROLE_ASSISTANT,
            content_text=prev_output,
        ) | {"run_url": run_url}
        extra_content = assistant_extra_content(state, prev_output)
        if extra_content:
            assistant_entry["extra_content"] = extra_content

        # append previous input to the history
        ret["messages"] = state.get("messages", []) + [user_entry, assistant_entry]

    any_prev_input = prev_chat_input or state.get("input_prompt")
    if any_prev_input and sr.message_thread and sr.message_thread.last_run_id == sr.id:
        message_thread = sr.message_thread
    else:
        message_thread = None

    return ret, message_thread


def _build_chat_widget_edit_request_body(
    *,
    current_sr: SavedRun,
    state: dict,
    edit_sr: SavedRun,
    input_prompt: str | None,
) -> dict:
    """
    Re-run the turn that `edit_sr` produced, with new input. Its saved state
    already holds the history from *before* that turn, so everything the user
    said after it is dropped just by re-running it.
    """
    if edit_sr.uid != current_sr.uid:
        raise UserError("You can only edit messages in your own conversations.")
    if (edit_sr.run_id, edit_sr.uid) not in _editable_run_refs(current_sr, state):
        raise UserError("This message can no longer be edited.")

    # deep copy so mutating the request body can't touch the source run's state
    request_body = copy.deepcopy(edit_sr.state)
    request_body["input_prompt"] = input_prompt
    return request_body


def _editable_run_refs(current_sr: SavedRun, state: dict) -> set[tuple[str, str]]:
    """
    Every run the current conversation renders, as (run_id, uid).

    `url_to_runs` does no ownership check, so this is what stops a client from
    naming an arbitrary run and having its state — bot_script, documents,
    variables — copied into a run of their own. Built from the server's state,
    never from the request.
    """
    refs = {(current_sr.run_id, current_sr.uid)}
    for entry in state.get("messages") or []:
        run_url = entry.get("run_url")
        if not run_url:
            continue
        _, run_id, uid = extract_query_params(yarl.URL(run_url).query)
        if run_id and uid:
            refs.add((run_id, uid))
    return refs


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


def assistant_extra_content(state: dict, raw_output_text: str) -> dict[str, Any]:
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
    from daras_ai_v2.bots import parse_bot_html

    for entry in entries:
        role = entry.get("role")

        run_url = entry.get("run_url")
        extra_content = entry.get("extra_content") or {}
        text = extra_content.get("display_content", get_entry_text(entry)) or ""
        audio = extra_content.get("audio")
        video = extra_content.get("video")
        documents = extra_content.get("documents")

        if role == CHATML_ROLE_USER:
            msg = dict(
                role=role,
                input_prompt=text,
                input_images=get_entry_images(entry) or [],
            )
            if run_url:
                # the widget only offers to edit a message it can point at a run
                msg["web_url"] = run_url
            if created_at := entry.get("created_at"):
                msg["created_at"] = created_at
            if audio:
                msg["input_audio"] = audio
            if documents:
                msg["input_documents"] = documents
            yield msg

        elif role == CHATML_ROLE_ASSISTANT:
            text = parse_bot_html(text)[1]
            # buttons, text = parse_bot_html(text)[:2]
            msg = dict(
                role=role,
                type="final_response",
                status="completed",
                output_text=[text],
                buttons=[],
            )
            if run_url:
                msg["web_url"] = run_url
            if audio:
                msg["output_audio"] = audio
            if video:
                msg["output_video"] = video
            yield msg
