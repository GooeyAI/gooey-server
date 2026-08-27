import html
import json
import traceback
import typing
from enum import Enum
from functools import cached_property
from itertools import zip_longest

import sentry_sdk

import gooey_gui as gui
from ai_models.models import AIModelSpec
from bots.models import (
    BotIntegration,
    Platform,
    SavedRun,
)
from bots.models.message_thread import MessageThread
from daras_ai_v2 import exceptions, icons, settings
from daras_ai_v2.asr import (
    run_translate,
    should_translate_lang,
)
from daras_ai_v2.base import STARTING_STATE
from daras_ai_v2.base_v2 import (
    FILL_HEIGHT_EDITOR_CSS,
    VARIABLES_DIALOG_CSS,
    BasePage,
    RecipeTabs,
)
from daras_ai_v2.bot_integration_widgets import integrations_welcome_screen
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    cache_knowledge_widget,
    citation_style_selector,
    doc_extract_selector,
    doc_search_advanced_settings,
    keyword_instructions_widget,
    query_instructions_widget,
)
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.fastapi_tricks import get_api_route_url
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.integrations_tab import render_integrations_tab
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    SUPERSCRIPT,
    run_language_model,
)
from daras_ai_v2.language_model_openai_audio import is_realtime_audio_url
from daras_ai_v2.language_model_settings_widgets import (
    language_model_selector,
)
from daras_ai_v2.search_ref import (
    CitationStyles,
    apply_response_formattings_prefix,
    apply_response_formattings_suffix,
    parse_refs,
)
from daras_ai_v2.tab_spec import PaneSpec, RecipeView, TabSpec
from daras_ai_v2.text_output_widget import text_output
from daras_ai_v2.text_to_speech_settings_widgets import (
    TextToSpeechProviders,
)
from daras_ai_v2.web_widget_embed import (
    get_chat_widget_messages,
    load_chat_widget_lib,
)
from functions.base_llm_tool import (
    BaseLLMTool,
    get_tool_from_call,
    render_called_functions,
)
from functions.models import FunctionTrigger
from functions.workflow_tools import DynamicLLMToolLoader
from gooey_gui.types.recipe_top_bar_props import TopBarIntegration
from gooey_gui.types.recipe_workspace_props import RecipeWorkspaceTriggerProps

# Extends the v1 recipe rather than copying it: the 33 members that were byte-identical are
# inherited now, and so are the module-level helpers below. What is left in this file is the
# v2 presentation - the config panes, the About cards, the top bar chips - plus the handful of
# render methods that differ.
from recipes.VideoBots import (
    DEFAULT_TRANSLATION_MODEL,
    VideoBotsPage,
    _can_use_message_thread,
)
from widgets.switch_with_section import switch_with_section
from widgets.workflow_bulk_runs_list import render_workflow_bulk_runs_list

# The "Model <selector>" row above the instructions editor.
MODEL_ROW_CSS = """
/* app.css gives `.gui-input` a `margin-bottom: .9rem` meant for stacked form fields; on a
   one-line row it just pushes the editor down. Scoped rather than changed on the widget:
   `.<hash> .gui-input` outranks a bare `.gui-input`, so it needs no `!important` and leaks
   nowhere. */
& .gui-input {
    margin-bottom: 0;
}

/* Match the pane strip's pills (PANE_STRIP_CSS: 0.875rem). Neither react-select nor
   `AIModelSpec.display_html()` sets a font size, so the control was inheriting the page's 1rem
   and reading a size larger than the tabs directly above it. Set on the wrapper so the value,
   the placeholder and the open menu all shift together. */
& .gui-input-select {
    font-size: 0.875rem;
}

/* ...and the pills' 10px corners. `gui.selectbox` renders react-select with no
   `classNamePrefix`, so its control has only emotion-generated classes (`css-xxxxx-control`) -
   hence the attribute match on the one stable part of that name. Scoped under two classes, so
   it outranks emotion's own single-class rule without `!important`.
   If we end up restyling selects in more than this one place, the better fix is to add
   `classNamePrefix` in GooeySelect.tsx and target `.gooey-select__control` everywhere. */
& .gui-input-select [class*="-control"] {
    border-radius: 10px;
}
"""


# `(str, Enum)` rather than `enum.StrEnum`: this runs on 3.10, where StrEnum does not exist.
# Matching `BulkRunnerRunState` in gooey_gui/types/bulk_progress_props.py.
class ConfigPane(str, Enum):
    """Stable ids for the working column's panes.

    These are what session state and the About cards' deep links carry, so they must not
    change; the labels beside them in `_config_panes()` are display-only and can.
    """

    llm_instructions = "llm-instructions"
    knowledge = "knowledge"
    tools = "tools"
    settings = "settings"
    debug = "debug"


class VideoBotsPageV2(BasePage, VideoBotsPage):
    """The agent recipe in layout v2.

    Two bases, and the order matters. `BasePage` is the v2 shell - the app frame, the top bar,
    the workspace - and it has to come first, or v1's `render` would win and this page would
    draw the old layout. `VideoBotsPage` brings everything that makes it *this* recipe: the
    request and response models, the inference pipeline, the cost maths. Both descend from the
    v1 base, so the MRO is a straight line: v2 presentation over v1 recipe over v1 base.
    """

    @classmethod
    def get_runner_page_cls(cls):
        return VideoBotsPage

    # Both of these suppress a renderer the v2 base provides, and both have to be declared
    # here rather than left to the MRO: `BasePage` sits ahead of `VideoBotsPage`, so the
    # base's version would otherwise win over the recipe's.
    def render_form_v2(self):
        # v2 builds the form out of config panes instead - see `_config_panes`.
        pass

    def _render_regenerate_button(self):
        # A chat has no seed to re-roll, so there is nothing to regenerate.
        pass

    def run_v2(
        self,
        request: "VideoBotsPageV2.RequestModel",
        response: "VideoBotsPageV2.ResponseModel",
    ) -> typing.Iterator[str | None]:
        if request.tts_provider == TextToSpeechProviders.ELEVEN_LABS.name and not (
            self.is_current_user_paying() or self.is_current_user_admin()
        ):
            raise UserError(
                """
                Please purchase Gooey.AI credits to use ElevenLabs voices <a href="/account">here</a>.
                """
            )

        try:
            llm_model = AIModelSpec.objects.get(name=request.selected_model)
        except AIModelSpec.DoesNotExist:
            raise UserError(
                f"Model {request.selected_model} not found. Should be one of: "
                + ", ".join(
                    AIModelSpec.objects.filter(category=AIModelSpec.Categories.llm)
                    .order_for_frontend()
                    .values_list("name", flat=True)
                )
            )
        user_input = (request.input_prompt or "").strip()
        if not (
            user_input
            or request.input_audio
            or request.input_images
            or request.input_documents
        ):
            return

        asr_msg, user_input = yield from self.asr_step(
            model=llm_model, request=request, response=response, user_input=user_input
        )

        ocr_texts = yield from self.document_understanding_step(request=request)

        request.translation_model = (
            request.translation_model or DEFAULT_TRANSLATION_MODEL
        )
        user_input = yield from self.input_translation_step(
            request=request, user_input=user_input, ocr_texts=ocr_texts
        )

        tools_by_name = self.get_current_llm_tools()

        yield from self.build_final_prompt(
            request=request,
            response=response,
            user_input=user_input,
            model=llm_model,
            tools_by_name=tools_by_name,
            # use LLM audio input capability if not using a dedicated ASR model
            include_input_audio=(
                not asr_msg and not is_realtime_audio_url(request.input_audio)
            ),
        )

        yield from self.llm_loop(
            request=request,
            response=response,
            model=llm_model,
            asr_msg=asr_msg,
            tools_by_name=tools_by_name,
        )

        yield from self.tts_step(model=llm_model, request=request, response=response)

        yield from self.lipsync_step(request, response)

    def llm_loop(
        self,
        *,
        request: "VideoBotsPageV2.RequestModel",
        response: "VideoBotsPageV2.ResponseModel",
        model: AIModelSpec,
        asr_msg: str | None = None,
        prev_output_text: list[str] | None = None,
        tools_by_name: dict[str, BaseLLMTool],
    ) -> typing.Iterator[str | None]:
        from functions.gooey_builder_tools import get_current_builder_tools

        yield f"Summarizing with {model.label}..."

        audio_session_extra = None
        if model.llm_is_audio_model:
            audio_session_extra = {}
            if request.openai_voice_name:
                audio_session_extra["voice"] = request.openai_voice_name

        tools_by_name |= get_current_builder_tools(self.current_sr)

        loader = DynamicLLMToolLoader(tools_by_name, self.active_tool_names)
        tools_by_name[loader.name] = loader
        active_tools = [
            tool for tool in tools_by_name.values() if loader.is_tool_active(tool)
        ]
        response.final_prompt[0]["tools"] = [
            tool.spec_function for tool in active_tools
        ]

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

            output_text = yield from self.output_translation_step(
                request, response, output_text
            )

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
                else:
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

        yield from self.llm_loop(
            request=request,
            response=response,
            model=model,
            prev_output_text=output_text,
            tools_by_name=tools_by_name,
        )

    def output_translation_step(self, request, response, output_text):
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

    def _render_running_output(self):
        # The embedded widget renders its own running state. Do not call scrollIntoView:
        # the v2 app shell keeps its header outside the body scroller.
        return

    def render_output(self):
        gui.tag(
            "button",
            type="submit",
            name="onSendMessage",
            hidden=True,
            id="onSendMessage",
        )
        input_payload = gui.session_state.pop("onSendMessage", None)
        if input_payload:
            try:
                input_data = json.loads(input_payload)
            except (json.JSONDecodeError, TypeError):
                pass
            else:
                self.on_send(input_data)

        gui.tag(
            "button",
            type="submit",
            name="onNewConversation",
            value="yes",
            hidden=True,
            id="onNewConversation",
        )
        if gui.session_state.pop("onNewConversation", None):
            gui.session_state["messages"] = []
            gui.session_state["input_prompt"] = ""
            gui.session_state["input_images"] = None
            gui.session_state["input_audio"] = None
            gui.session_state["input_documents"] = None
            gui.session_state["raw_input_text"] = ""
            self.clear_outputs()
            gui.session_state["final_keyword_query"] = ""
            gui.session_state["final_search_query"] = ""
            gui.rerun()

        messages = get_chat_widget_messages(gui.session_state)

        # fill branding with bot integration data if available
        bot_integration = (
            BotIntegration.objects.filter(
                published_run=self.current_pr,
                platform=Platform.WEB,
            )
            .order_by("-updated_at")
            .first()
        )
        if bot_integration:
            bot_branding = bot_integration.get_web_widget_branding()
        else:
            bot_branding = dict(
                name=self.current_pr.title,
                title=self.current_pr.title,
            )
        if self.current_pr.photo_url:
            bot_branding["photoUrl"] = self.current_pr.photo_url
        bot_branding["showPoweredByGooey"] = False

        config = dict(
            integration_id="magic",
            target="#gooey-embed",
            mode="inline",
            enableAudioMessage=True,
            enablePhotoUpload=True,
            enableConversations=True,
            showToolCalls=True,
            branding=bot_branding,
            fillParent=True,
            enableSourcePreview=False,
            secrets=dict(GOOGLE_MAPS_API_KEY=settings.GOOGLE_MAPS_API_KEY),
        )
        # the page's own top bar already names the agent, so the widget never needs its own
        config["showHeader"] = False
        if self._has_whatsapp_integration:
            config["theme"] = "whatsapp"
        if settings.DEBUG:
            from routers.bots_api import stream_create

            config["apiUrl"] = get_api_route_url(stream_create)

        load_chat_widget_lib()
        # Master's component: it renders #gooey-embed and mounts the widget into it once,
        # with theme, branding and messages reaching it through the controller afterwards.
        # v2 differs only in sizing - it fills the scrolling body area rather than the
        # viewport, because the top bar sits above this and `100vh` would overflow by
        # exactly the bar's height.
        gui.component(
            "GooeyEmbedPreview",
            config=config,
            messages=messages,
            run_url=str(self.request.url),
            style=dict(height="100%", minHeight=0),
        )

    @cached_property
    def _has_whatsapp_integration(self) -> bool:
        return BotIntegration.objects.filter(
            published_run=self.current_pr,
            platform=Platform.WHATSAPP,
        ).exists()

    def render_steps(self):
        if gui.session_state.get("tts_provider"):
            gui.video(gui.session_state.get("input_face"), caption="Input Face")

        final_search_query = gui.session_state.get("final_search_query")
        if final_search_query:
            gui.text_area(
                "###### `search_query`",
                value=str(final_search_query),
                disabled=True,
            )

        final_keyword_query = gui.session_state.get("final_keyword_query")
        if final_keyword_query:
            if isinstance(final_keyword_query, list):
                gui.write("###### `final_keyword_query`")
                gui.json(final_keyword_query)
            else:
                gui.text_area(
                    "###### `final_keyword_query`",
                    value=str(final_keyword_query),
                    disabled=True,
                )

        references = gui.session_state.get("references", [])
        if references:
            gui.write("###### `references`")
            gui.json(references, collapseStringsAfterLength=False)

        final_prompt = gui.session_state.get("final_prompt")
        if final_prompt:
            if isinstance(final_prompt, str):
                text_output("###### `final_prompt`", value=final_prompt, height=300)
            else:
                gui.write(
                    f"###### {icons.terminal} `final_prompt`",
                    unsafe_allow_html=True,
                )
                gui.json(final_prompt, depth=5)

        for k in ["raw_output_text", "output_text", "raw_tts_text"]:
            for idx, text in enumerate(gui.session_state.get(k) or []):
                gui.text_area(
                    f"###### 📜 `{k}[{idx}]`",
                    value=text,
                    disabled=True,
                )

        for idx, audio_url in enumerate(gui.session_state.get("output_audio", [])):
            gui.write(f"###### 🔉 `output_audio[{idx}]`")
            gui.audio(audio_url)

    DEMO_ACTION_PREFIX = "demo:"

    def _top_bar_integrations(self) -> list[TopBarIntegration]:
        """v1's demo buttons, as chips in the top bar.

        They open a dialog rather than navigating, so each carries an action key instead of
        an href and comes back through the bar's menu key.
        """
        from widgets.demo_button import get_demo_bots

        integrations = []
        for bi_id, platform_id in get_demo_bots(self.current_pr):
            platform = Platform(platform_id)
            integrations.append(
                TopBarIntegration(
                    # the chip opens a demo of the live bot, so it says so - v1 could get away
                    # with a bare platform name because its buttons sat under a "Demos" header
                    label=f"Try in {platform.get_title()}",
                    icon=platform.get_icon(),
                    color=platform.get_demo_button_color() or None,
                    key=f"{self.DEMO_ACTION_PREFIX}{bi_id}",
                )
            )
        return integrations

    def _handle_menu_pick(self, picked: str | None):
        """The demo chips, which come back through the same menu key the title menu uses.

        Extends rather than replaces: `super()` still handles Version history, Duplicate and
        Delete, so a chip key and a title-menu key can share one round trip without either
        having to know about the other.
        """
        super()._handle_menu_pick(picked)

        from widgets.demo_button import get_demo_bots, render_demo_dialog

        for bi_id, _ in get_demo_bots(self.current_pr):
            # the dialog has to be re-entered on every pass while it is open, so this runs
            # for each demo bot rather than only the one just clicked
            ref = gui.use_alert_dialog(key=f"demo-modal-{bi_id}")
            if picked == f"{self.DEMO_ACTION_PREFIX}{bi_id}":
                ref.set_open(True)
            if ref.is_open:
                render_demo_dialog(ref, bi_id)

    def render_header_extra(self):
        # v2 surfaces the demo buttons as chips in the top bar instead
        pass

    def entry_tab_slug(self, tabs: list[TabSpec]) -> RecipeView:
        """Show About to a first-time visitor and Split to everyone else.

        Someone who has arrived at a workflow they do not own wants to know what it is
        before they meet its knobs; someone opening their own run wants to work.
        """
        return RecipeView.about if self.is_unowned_example() else RecipeView.split

    def get_tab_spec(self) -> list[TabSpec]:
        """The agent tab set.

        Deploy is deliberately absent: it becomes a sub-tab of Config in a later slice, and
        until then its body stays reachable through v1's `/integrations/` url via
        `render_selected_tab()`.
        """
        if self.is_unowned_example():
            return self.get_viewer_tab_spec()
        return [
            TabSpec(
                slug=RecipeView.about,
                label="About",
                icon=icons.info,
            ),
            TabSpec(
                slug=RecipeView.edit,
                label="Edit",
                icon=icons.edit,
            ),
            TabSpec(
                slug=RecipeView.preview,
                label="Preview",
                icon=icons.preview,
                # Not immersive on a phone any more. It used to take the whole screen, which
                # meant hiding the top bar and giving the pane a floating back pill of its own
                # to make up for it. The bar is the app's only header now, and the design keeps
                # it on every screen - so the pane keeps the header, and the header's back
                # arrow is the way out. One piece of chrome instead of two.
            ),
            TabSpec(
                slug=RecipeView.split,
                label="Split",
                icon=icons.split,
                # two columns side by side - there is no room for it on a phone
                desktop_only=True,
            ),
        ]

    CONFIG_PANE_KEY = "--config-subtab"

    def _render_about_meta(self):
        """How this agent is put together: its model, what it knows, what it can do.

        Each card is a way into the Config pane that owns the setting, so About reads as a
        summary you can act on rather than a dead-end description.
        """
        model = self._about_model_summary()

        # Knowledge and Tools read as one idea - what the agent can reach outside itself -
        # so they share a group, leaving the model on its own as the thing it *is*.
        integrations: list[tuple[str, str, ConfigPane]] = []
        if documents := len(gui.session_state.get("documents") or []):
            plural = "" if documents == 1 else "s"
            integrations.append(
                (icons.library, f"{documents} document{plural}", ConfigPane.knowledge)
            )
        if tools := len(gui.session_state.get("functions") or []):
            plural = "" if tools == 1 else "s"
            integrations.append((icons.code, f"{tools} tool{plural}", ConfigPane.tools))

        # a row of zeroes says less than no row: skip the heading too, not just the cards
        if not model and not integrations:
            return

        with gui.div(className="v2-about-groups"):
            if model:
                self._render_about_meta_group(
                    "Model", [(*model, ConfigPane.llm_instructions)]
                )
            if integrations:
                self._render_about_meta_group("Tools & Integrations", integrations)

    def _render_about_meta_group(
        self, title: str, cards: list[tuple[str, str, ConfigPane]]
    ):
        with gui.div(className="v2-about-group"):
            gui.html(f'<div class="v2-about-section-title">{html.escape(title)}</div>')
            with gui.div(className="v2-about-meta"):
                for icon, label, pane in cards:
                    self._render_about_meta_card(icon=icon, label=label, pane=pane)

    def _about_model_summary(self) -> tuple[str, str] | None:
        """(icon html, label) for the selected LLM, or None if the run has not picked one."""
        name = gui.session_state.get("selected_model")
        if not name:
            return None
        spec = AIModelSpec.objects.filter(name=name).select_related("creator").first()
        if not spec:
            # a model that has since been removed - its name is still better than nothing
            return icons.sparkles, name
        return (spec.creator and spec.creator.html_icon()) or icons.sparkles, spec.label

    def _render_about_meta_card(self, *, icon: str, label: str, pane: ConfigPane):
        with gui.model_component(
            RecipeWorkspaceTriggerProps(
                storage_key=self._workspace_storage_key(),
                initial_view=self.entry_tab_slug(self.get_tab_spec()),
                view=RecipeView.edit,
                state_key=self.CONFIG_PANE_KEY,
                state_value=pane,
                className="v2-about-meta-card",
            )
        ):
            # icon over label, and no chevron: the whole card is the link, so an affordance
            # arrow only competed with the icon for the eye
            gui.html(
                f'<span class="v2-about-meta-icon">{icon}</span>'
                f'<span class="v2-about-meta-label">{html.escape(label)}</span>'
            )

    def _config_panes(self) -> list[PaneSpec]:
        """The working column's panes, in strip order.

        These regroup what v1 spread across `render_form_v2` and the Settings expander -
        every pane composes existing widgets, none of them reimplement anything.
        """
        return [
            PaneSpec(
                ConfigPane.llm_instructions,
                "LLM Instructions",
                self._render_llm_instructions_pane,
            ),
            PaneSpec(ConfigPane.knowledge, "Knowledge", self._render_knowledge_pane),
            # functions only - the variables half of v1's block moved to a dialog beside the
            # prompt. Rendering it here too would mean two editors on the same widget keys.
            PaneSpec(ConfigPane.tools, "Tools", self._render_functions),
            PaneSpec(ConfigPane.settings, "Settings", self._render_settings_pane),
            PaneSpec(ConfigPane.debug, "Debug", self._render_debug_pane),
        ]

    def _render_input_col(self):
        """The working column, shared by Config (alone) and Split (beside the preview).

        Overriding this - rather than the tabs - is what gives both of them the pane strip
        without duplicating the layout.
        """
        with gui.div(className="d-flex flex-column h-100", style=dict(minHeight=0)):
            # strip and submit row are fixed; only the pane between them scrolls, and only
            # when its content actually overflows
            render_pane = self._render_pane_strip(
                self._config_panes(), key=self.CONFIG_PANE_KEY
            )
            with gui.div(
                # pe-3 keeps the scrollbar off the content when the pane overflows
                className="flex-grow-1 overflow-auto pt-2 pe-1 pe-lg-3",
                style=dict(minHeight=0),
            ):
                render_pane()

        # nothing in this column submits any more; the top bar owns Run
        return False

    def _render_variables_button(self):
        """Variables live beside the prompt that references them, not on a pane of their own.

        The editor is a list of name/value rows that would crowd this pane and steal height
        from the instructions, so the button carries the count and the editing happens in a
        dialog. The count comes from `variable_names()`, which reads the prompt directly -
        so it is right even before the editor has ever been opened.
        """
        ref = gui.use_alert_dialog(key="variables-modal")
        # "(0)" reads as a broken counter rather than an empty list, so it is left off
        count = len(self.variable_names())
        if gui.button(
            f"{icons.variables} Variables" + (f" ({count})" if count else ""),
            type="tertiary",
            # ms-auto pushes it to the far end of the row, opposite the model selector.
            # fw-normal + small because `.btn.btn-theme` is bold at body size, and a
            # secondary action next to a form field should not shout louder than the field's
            # own label.
            className="mb-0 p-2 text-nowrap ms-auto fw-normal small",
            key="open-variables",
        ):
            ref.set_open(True)
        if not ref.is_open:
            return

        with (
            gui.alert_dialog(ref=ref, modal_title="#### Variables", large=True),
            gui.styled(VARIABLES_DIALOG_CSS),
            gui.div(),
        ):
            # kept whether or not any exist: the editor never says where variables come
            # from, and most are declared by writing them into the prompt, not added here
            with gui.div(className="container-margin-reset mb-3"):
                gui.caption(
                    "Variables let you pass custom parameters into this agent.  \n"
                    "Reference one in your instructions with Jinja - "
                    "`{{ my_variable }}` - and it appears here to fill in. "
                    "[Learn more](/variables-help)."
                )
            self._render_variables_editor(heading=False)

    def _render_llm_instructions_pane(self):
        """Model selector pinned on top, editor filling whatever height is left.

        v1 capped the editor at `maxHeight: 50vh`, which in an app shell leaves dead space
        below it on tall screens and still overflows on short ones.
        """
        with gui.div(className="d-flex flex-column h-100", style=dict(minHeight=0)):
            # a compact row - small label left, selector right - rather than v1's full-width
            # heading and field, so the editor gets the height instead.
            with (
                gui.styled(MODEL_ROW_CSS),
                gui.div(className="d-flex align-items-center gap-3 mb-2 flex-shrink-0"),
            ):
                gui.html('<span class="text-muted small">Model</span>')
                # a fixed width rather than a percentage: the selector holds one model name,
                # so it should not keep growing with the pane. Capped as a share of the pane
                # too, so it still fits when the Builder squeezes the column.
                with gui.div(
                    style=dict(width="14rem", maxWidth="45%"), className="m-0"
                ):
                    language_model_selector(label="")
                self._render_variables_button()

            with (
                gui.styled(FILL_HEIGHT_EDITOR_CSS),
                gui.div(
                    className="flex-grow-1 d-flex flex-column", style=dict(minHeight=0)
                ),
            ):
                gui.code_editor(
                    label="",
                    key="bot_script",
                    language="jinja",
                    help=field_desc(self.RequestModel, "bot_script"),
                )

    def _render_knowledge_pane(self):
        # v1 gated this on language_model_selector's RETURN VALUE, which only exists while
        # that widget renders. It lives on another pane now, so read the state key instead -
        # otherwise the uploader silently disappears unless LLM Instructions rendered first.
        if not AIModelSpec.objects.filter(
            name=gui.session_state.get("selected_model"), llm_is_audio_model=True
        ).exists():
            bulk_documents_uploader(
                label=(
                    f"#### {icons.books} " + field_title(self.RequestModel, "documents")
                ),
                accept=["audio/*", "application/*", "video/*", "text/*"],
                help=field_desc(self.RequestModel, "documents"),
            )

        if not gui.session_state.get("documents"):
            return

        gui.write("#### 📄 Knowledge Base")
        gui.text_area(
            "###### 👩‍🏫 " + field_title(self.RequestModel, "task_instructions"),
            help=field_desc(self.RequestModel, "task_instructions"),
            key="task_instructions",
            height=300,
        )
        citation_style_selector()
        gui.checkbox("🔗 Shorten citation links", key="use_url_shortener")
        cache_knowledge_widget(self)
        doc_extract_selector(self.request.user)

        gui.write("---")
        query_instructions_widget()
        keyword_instructions_widget()
        gui.write("---")
        doc_search_advanced_settings()

    def _render_settings_pane(self):
        gui.markdown("#### 💪 Capabilities")

        speech_recognition_enabled = switch_with_section(
            label="##### 🦻 Speech Recognition & Translation",
            key="_speech_recognition_enabled",
            control_keys=["user_language", "asr_model"],
            render_section=self.speech_recognition_settings,
        )
        if not speech_recognition_enabled:
            gui.session_state["asr_model"] = None
            gui.session_state["asr_language"] = None
            gui.session_state["asr_prompt"] = None
            gui.session_state["asr_task"] = None
            gui.session_state["translation_model"] = None
            gui.session_state["user_language"] = None

        text_to_speech_enabled = switch_with_section(
            label="##### 🗣️ Text to Speech & Lipsync",
            key="_text_to_speech_enabled",
            control_keys=["tts_provider"],
            render_section=self.text_to_speech_settings,
        )
        if not text_to_speech_enabled:
            gui.session_state["tts_provider"] = None

        document_intelligence_enabled = switch_with_section(
            label="##### 🩻 Photo & Document Intelligence",
            key="_document_intelligence_enabled",
            control_keys=["document_model"],
            render_section=self.document_intelligence_settings,
        )
        if not document_intelligence_enabled:
            gui.session_state["document_model"] = None

        switch_with_section(
            label="##### 📊 Analytics & Evaluation",
            control_keys=["bulk_runs"],
            render_section=lambda: render_workflow_bulk_runs_list(
                user=self.request.user,
                workspace=self.request.user and self.current_workspace,
                sr=self.current_sr,
                pr=self.current_pr,
            ),
        )

        gui.write("---")
        self.render_settings()

    def _render_debug_pane(self):
        render_called_functions(saved_run=self.current_sr, trigger=FunctionTrigger.pre)
        self.render_steps()
        render_called_functions(saved_run=self.current_sr, trigger=FunctionTrigger.post)
        gui.caption(
            f"""
            Run Time: {self.current_sr.run_time.total_seconds():.2f}s\n\n
            [Parent Run]({self.current_sr.parent and self.current_sr.parent.get_app_url()})
            """,
            unsafe_allow_html=True,
        )

    def _render_deploy_panel(self):
        """Deploy's body. Reached two ways - the Config sub-tab, and v1's `/integrations/`
        deep link via `render_selected_tab()` - so it lives in exactly one place.
        """
        user = self.request.user
        # not signed in case
        if not user or user.is_anonymous:
            integrations_welcome_screen(title="Connect your Agent")
            gui.newline()
            with gui.center():
                gui.anchor("Get Started", href=self.get_auth_url(), type="primary")
            return
        sr, pr = self.current_sr_pr
        render_integrations_tab(
            user=self.request.user,
            workspace=self.current_workspace,
            saved_run=sr,
            published_run=pr,
        )

    def render_selected_tab(self):
        if self.tab == RecipeTabs.integrations:
            self._render_deploy_panel()
        else:
            super().render_selected_tab()

    def create_new_run(
        self,
        *,
        enable_rate_limits: bool = False,
        run_status: str | None = STARTING_STATE,
        **defaults,
    ) -> SavedRun:
        message_thread = defaults.pop("message_thread", None)
        if not _can_use_message_thread(message_thread, self.request.user):
            message_thread = None

        sr = super().create_new_run(
            enable_rate_limits=enable_rate_limits,
            run_status=run_status,
            message_thread=message_thread,
            **defaults,
        )

        if message_thread:
            if not message_thread.first_run:
                message_thread.first_run = sr
            message_thread.last_run = sr
            message_thread.save(update_fields=["first_run", "last_run"])
        else:
            message_thread = MessageThread.objects.create(
                title=gui.session_state.get("input_prompt") or "",
                first_run=sr,
                last_run=sr,
            )
            sr.message_thread = message_thread
            sr.save(update_fields=["message_thread"])

        return sr
