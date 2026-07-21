from typing import Any

from bots.models import SavedRun
from bots.models.message_thread import MessageThread
import gooey_gui as gui

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


def chat_widget_input_to_request_body(
    sr: SavedRun, state: dict, input_data: dict
) -> tuple[dict, MessageThread | None]:
    from daras_ai_v2.bots import handle_location_msg

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
        # append previous input to the history
        ret["messages"] = state.get("messages", []) + [
            format_chat_entry(
                role=CHATML_ROLE_USER,
                content_text=prev_input,
                input_images=prev_input_images,
                # input_audio=prev_input_audio,
                input_documents=prev_input_documents,
            ),
            format_chat_entry(
                role=CHATML_ROLE_ASSISTANT,
                content_text=prev_output,
            ),
        ]

    any_prev_input = prev_chat_input or state.get("input_prompt")
    if any_prev_input and sr.message_thread and sr.message_thread.last_run_id == sr.id:
        message_thread = sr.message_thread
    else:
        message_thread = None

    return ret, message_thread


def get_chat_widget_messages(state: dict, web_url: str | None = None) -> list[Any]:
    from daras_ai_v2.bots import parse_bot_html
    from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys

    messages = []  # chat widget internal mishmash format
    input_audio = state.get("input_audio") or ""
    input_images = state.get("input_images") or []
    input_documents = state.get("input_documents") or []

    if is_realtime_audio_url(input_audio):
        entries = state.get("final_prompt", []).copy()
        input_audio = ""  # dont render ws audio url in chat widget
    else:
        entries = state.get("messages", []).copy()

    for entry in entries:
        role = entry.get("role")
        if role == CHATML_ROLE_USER:
            messages.append(
                dict(
                    role=role,
                    input_prompt=get_entry_text(entry),
                    input_images=get_entry_images(entry) or [],
                )
            )
        elif role == CHATML_ROLE_ASSISTANT:
            messages.append(
                dict(
                    role=role,
                    type="final_response",
                    status="completed",
                    output_text=[parse_bot_html(get_entry_text(entry))[1]],
                )
            )

    # add last input to history if present
    show_raw_msgs = False
    if show_raw_msgs:
        input_prompt = state.get("raw_input_text") or ""
    else:
        input_prompt = state.get("input_prompt") or ""

    if input_prompt or input_images or input_audio or input_documents:
        messages.append(
            dict(
                role=CHATML_ROLE_USER,
                input_prompt=input_prompt,
                input_images=input_images,
                input_audio=input_audio,
                input_documents=input_documents,
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
