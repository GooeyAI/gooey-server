from __future__ import annotations

import json
import traceback
import typing
from itertools import zip_longest

import sentry_sdk

from ai_models.models import AIModelSpec
from daras_ai_v2 import exceptions
from daras_ai_v2.asr import run_translate, should_translate_lang
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    SUPERSCRIPT,
    run_language_model,
)
from daras_ai_v2.search_ref import (
    CitationStyles,
    apply_response_formattings_prefix,
    apply_response_formattings_suffix,
    parse_refs,
)
from functions.base_llm_tool import BaseLLMTool, get_tool_from_call
from functions.workflow_tools import DynamicLLMToolLoader

if typing.TYPE_CHECKING:
    from bots.models import SavedRun
    from recipes.VideoBots import VideoBotsPage


def llm_loop(
    *,
    request: VideoBotsPage.RequestModel,
    response: VideoBotsPage.ResponseModel,
    model: AIModelSpec,
    asr_msg: str | None = None,
    prev_output_text: list[str] | None = None,
    tools_by_name: dict[str, BaseLLMTool] | None = None,
    current_sr: SavedRun | None = None,
    active_tool_names: set[str] | None = None,
) -> typing.Iterator[str | None]:
    yield f"Summarizing with {model.label}..."

    if tools_by_name is None:
        tools_by_name = {}
    if active_tool_names is None:
        active_tool_names = set()

    audio_session_extra = None
    if model.llm_is_audio_model:
        audio_session_extra = {}
        if request.openai_voice_name:
            audio_session_extra["voice"] = request.openai_voice_name

    if current_sr is not None:
        from functions.gooey_builder_tools import get_current_builder_tools

        tools_by_name |= get_current_builder_tools(current_sr)

    loader = DynamicLLMToolLoader(tools_by_name, active_tool_names)
    tools_by_name[loader.name] = loader
    active_tools = [
        tool for tool in tools_by_name.values() if loader.is_tool_active(tool)
    ]
    response.final_prompt[0]["tools"] = [tool.spec_function for tool in active_tools]

    chunks: typing.Generator[list[dict], None, None] = run_language_model(
        model=model.name,
        messages=response.final_prompt,
        max_tokens=request.max_tokens,
        num_outputs=request.num_outputs,
        temperature=request.sampling_temperature,
        avoid_repetition=request.avoid_repetition,
        response_format_type=request.response_format_type,
        reasoning_effort=request.reasoning_effort,
        tools=active_tools,
        stream=True,
        audio_url=request.input_audio,
        audio_session_extra=audio_session_extra,
    )

    tool_calls = None
    output_text = None
    response.final_prompt.append({"role": CHATML_ROLE_ASSISTANT, "content": ""})

    for i, choices in enumerate(chunks):
        if not choices:
            continue

        metrics = choices[0].get("metrics")
        if metrics:
            response.metrics = metrics

        output_text = [
            "\n\n".join(filter(None, (prev_text, entry.get("content"))))
            for prev_text, entry in zip_longest(
                (prev_output_text or []), choices, fillvalue=""
            )
        ]
        response.final_prompt[-1]["content"] = choices[0]["content"] or ""

        tool_calls = choices[0].get("tool_calls")
        if tool_calls:
            for call in tool_calls:
                tool = tools_by_name[call["function"]["name"]]
                call["label"] = tool.label
                call["icon"] = tool.get_icon()
            response.final_prompt[-1]["tool_calls"] = tool_calls

        try:
            response.raw_input_text = choices[0]["input_audio_transcript"]
        except KeyError:
            pass
        try:
            response.output_audio += [choices[0]["audio_url"]]
        except KeyError:
            pass

        # save raw model response without citations and translation for history
        response.raw_output_text = [
            "".join(snippet for snippet, _ in parse_refs(text, response.references))
            for text in output_text
        ]

        output_text = yield from output_translation_step(request, response, output_text)

        if response.references:
            citation_style = (
                request.citation_style and CitationStyles[request.citation_style]
            ) or None
            all_refs_list = apply_response_formattings_prefix(
                output_text, response.references, citation_style
            )
        else:
            citation_style = None
            all_refs_list = None

        if asr_msg:
            output_text = [asr_msg + "\n\n" + text for text in output_text]

        response.output_text = output_text

        finish_reason = [entry.get("finish_reason") for entry in choices]
        if all(finish_reason):
            if all_refs_list:
                apply_response_formattings_suffix(
                    all_refs_list, response.output_text, citation_style
                )
            response.finish_reason = finish_reason
        else:
            yield f"Streaming{str(i + 1).translate(SUPERSCRIPT)} {model.label}..."

    if response.output_text:
        response.output_text = [text.strip() for text in response.output_text]

    if not tool_calls:
        return
    for call in tool_calls:
        tool, arguments = get_tool_from_call(call["function"], tools_by_name)
        if not arguments:
            continue
        yield f"🛠 {tool.label}..."
        try:
            output = tool.call_json(arguments)
        except Exception as e:
            output = json.dumps(dict(error=str(e)))
            error_type = getattr(e, "error_type", type(e).__name__)
            if error_type and exceptions.get_error_renderer(error_type):
                # bubble up error so the parent run's standard error pipeline renders it
                raise
            traceback.print_exc()
            sentry_sdk.capture_exception(e)
        finally:
            response.final_prompt.append(
                dict(
                    role="tool",
                    content=output,
                    tool_call_id=call["id"],
                    run_url=tool.get_url(),
                ),
            )

    yield from llm_loop(
        request=request,
        response=response,
        model=model,
        prev_output_text=output_text,
        tools_by_name=tools_by_name,
        current_sr=current_sr,
        active_tool_names=active_tool_names,
    )


def output_translation_step(
    request: VideoBotsPage.RequestModel,
    response: VideoBotsPage.ResponseModel,
    output_text: list[str],
) -> typing.Generator[str, None, list[str]]:
    from daras_ai_v2.bots import parse_bot_html

    # translate response text
    if should_translate_lang(request.user_language):
        yield f"Translating response to {request.user_language}..."
        output_text = run_translate(
            texts=output_text,
            source_language="en",
            target_language=request.user_language,
            glossary_url=request.output_glossary_document,
            model=request.translation_model,
        )
        # save translated response for tts
        tts_source = [
            "".join(snippet for snippet, _ in parse_refs(text, response.references))
            for text in output_text
        ]
        response.raw_tts_text = tts_source
    else:
        tts_source = output_text

    # remove html tags from the output text for tts
    raw_tts_text = [parse_bot_html(text)[1].strip() for text in tts_source]
    if raw_tts_text != output_text:
        response.raw_tts_text = raw_tts_text

    return output_text
