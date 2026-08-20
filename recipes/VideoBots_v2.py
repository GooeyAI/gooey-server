import html
import json
from enum import Enum
from functools import cached_property

import gooey_gui as gui
from ai_models.models import AIModelSpec
from bots.models import BotIntegration, Platform, SavedRun
from bots.models.message_thread import MessageThread
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import icons, settings
from daras_ai_v2.asr import (
    AsrModels,
    TranslationModels,
    asr_language_selector,
    asr_model_selector,
    translation_language_selector,
    translation_model_selector,
)
from daras_ai_v2.base_v2 import (
    FILL_HEIGHT_EDITOR_CSS,
    STARTING_STATE,
    VARIABLES_DIALOG_CSS,
    BasePage,
    RecipeTabs,
)
from daras_ai_v2.bot_integration_widgets import integrations_welcome_screen
from daras_ai_v2.bots import parse_bot_html
from daras_ai_v2.doc_search_settings_widgets import (
    SUPPORTED_SPREADSHEET_TYPES,
    bulk_documents_uploader,
    cache_knowledge_widget,
    citation_style_selector,
    doc_extract_selector,
    doc_search_advanced_settings,
    keyword_instructions_widget,
    query_instructions_widget,
)
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.fastapi_tricks import get_api_route_url
from daras_ai_v2.field_render import field_desc, field_title, field_title_desc
from daras_ai_v2.integrations_tab import render_integrations_tab
from daras_ai_v2.language_filters import (
    asr_languages_without_dialects,
    language_filter_selector,
    tts_languages_without_dialects,
)
from daras_ai_v2.language_model_settings_widgets import (
    language_model_selector,
    language_model_settings,
)
from daras_ai_v2.lipsync_api import LipsyncModel
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.tab_spec import PaneSpec, RecipeView, TabSpec
from daras_ai_v2.text_output_widget import text_output
from daras_ai_v2.text_to_speech_settings_widgets import (
    elevenlabs_load_state,
    text_to_speech_provider_selector,
    text_to_speech_settings,
)
from daras_ai_v2.web_widget_embed import (
    get_chat_widget_messages,
    load_chat_widget_lib,
)
from functions.base_llm_tool import render_called_functions
from functions.models import FunctionTrigger
from gooey_gui.types.recipe_top_bar_props import TopBarIntegration
from recipes.DocExtract import document_intelligence_settings
from recipes.VideoBots import (
    DEFAULT_TRANSLATION_MODEL,
    VideoBotsPage,
    _can_use_message_thread,
    run_conversation_title_generator,
    should_create_thread_for_run,
)
from widgets.demo_button import get_demo_bots, render_demo_dialog
from widgets.switch_with_section import switch_with_section
from widgets.workflow_bulk_runs_list import render_workflow_bulk_runs_list


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


class ConfigPane(str, Enum):
    """Stable ids for the working column's panes.

    These are what session state and the About cards' deep links carry, so they must not
    change; the labels beside them in `_config_panes()` are display-only and can.
    """

    llm_instructions = "llm-instructions"
    knowledge = "knowledge"
    tools = "tools"
    settings = "settings"
    deploy = "deploy"
    debug = "debug"


class VideoBotsPageV2(BasePage):
    title = VideoBotsPage.title
    explore_image = VideoBotsPage.explore_image
    workflow = VideoBotsPage.workflow
    slug_versions = VideoBotsPage.slug_versions
    functions_in_settings = VideoBotsPage.functions_in_settings
    sane_defaults = VideoBotsPage.sane_defaults
    PROFIT_CREDITS = VideoBotsPage.PROFIT_CREDITS
    RequestModel = VideoBotsPage.RequestModel
    ResponseModel = VideoBotsPage.ResponseModel
    scroll_into_view = False
    DEMO_ACTION_PREFIX = "demo:"
    CONFIG_PANE_KEY = "--config-subtab"

    # UI still calls these; Celery must not grow a second copy of the recipe.
    validate_form_v2 = VideoBotsPage.validate_form_v2
    on_send = VideoBotsPage.on_send
    get_raw_price = VideoBotsPage.get_raw_price
    additional_notes = VideoBotsPage.additional_notes
    related_workflows = VideoBotsPage.related_workflows
    get_example_preferred_fields = classmethod(
        VideoBotsPage.get_example_preferred_fields.__func__
    )
    get_run_title = classmethod(VideoBotsPage.get_run_title.__func__)
    get_prompt_title = classmethod(VideoBotsPage.get_prompt_title.__func__)

    @classmethod
    def get_runner_page_cls(cls):
        """Celery must pickle VideoBotsPage, not this UI fork."""
        return VideoBotsPage

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
        elif should_create_thread_for_run(sr):
            message_thread = MessageThread.objects.create(
                title=gui.session_state.get("input_prompt") or "",
                first_run=sr,
                last_run=sr,
            )
            sr.message_thread = message_thread
            sr.save(update_fields=["message_thread"])

        if message_thread:
            run_conversation_title_generator(sr, self.request.user)

        return sr

    def speech_recognition_settings(self):
        with gui.div(className="pt-2 ps-1"):
            gui.caption(field_desc(self.RequestModel, "user_language"))

            # drop down to filter models based on the selected language
            selected_filter_language = language_filter_selector(
                options=asr_languages_without_dialects(),
                key="asr_language_filter",
            )

            col1, col2 = gui.columns(2)
            with col1:
                asr_model = asr_model_selector(
                    key="asr_model",
                    language_filter=selected_filter_language,
                    label=f"###### {field_title(self.RequestModel, 'asr_model')}",
                    format_func=lambda x: (AsrModels[x].value if x else "Auto Select"),
                )
            with col2:
                if asr_model:
                    asr_language = asr_language_selector(
                        asr_model,
                        language_filter=selected_filter_language,
                        label=f"###### {field_title(self.RequestModel, 'asr_language')}",
                        key="asr_language",
                    )
                else:
                    asr_language = None

            if asr_model and asr_model.supports_input_prompt():
                gui.text_area(
                    f"###### {field_title_desc(self.RequestModel, 'asr_prompt')}",
                    key="asr_prompt",
                    value="Transcribe the recording as accurately as possible.",
                    height=300,
                )

            gui.newline()
            if gui.checkbox(
                "🔠 **Translate to & from English**",
                value=bool(gui.session_state.get("translation_model")),
            ):
                gui.caption(
                    "Choose an AI model & language to translate incoming text & audio messages to English and responses back your selected language. Useful for low-resource languages."
                )

                if asr_model and asr_model.supports_speech_translation():
                    with gui.div(className="text-muted"):
                        if gui.checkbox(
                            label=field_desc(self.RequestModel, "asr_task").format(
                                asr_model=asr_model.value,
                                asr_language=asr_language or "Detected Language",
                            ),
                            value=gui.session_state.get("asr_task") == "translate",
                        ):
                            gui.session_state["asr_task"] = "translate"
                        else:
                            gui.session_state.pop("asr_task", None)
                else:
                    gui.session_state.pop("asr_task", None)

                col1, col2 = gui.columns(2)
                with col1:
                    translation_model = translation_model_selector(
                        allow_none=False,
                        language_filter=selected_filter_language,
                    )
                with col2:
                    translation_language_selector(
                        model=translation_model,
                        language_filter=selected_filter_language,
                        label=f"###### {field_title(self.RequestModel, 'user_language')}",
                        key="user_language",
                    )
            else:
                gui.session_state["asr_task"] = None
                gui.session_state["translation_model"] = None
                gui.session_state["user_language"] = None
            gui.div(className="pb-1")

    def text_to_speech_settings(self):
        with gui.div(className="pt-2 ps-1"):
            selected_filter_language = language_filter_selector(
                options=tts_languages_without_dialects(),
                key="tts_language_filter",
            )
            text_to_speech_provider_selector(
                self, language_filter=selected_filter_language
            )

        gui.newline()

        if gui.checkbox(
            label="**🫦 Add Lipsync Video**",
            value=bool(gui.session_state.get("input_face")),
        ):
            self.lipsync_settings()
        else:
            gui.session_state["input_face"] = None
            gui.session_state.pop("lipsync_model", None)

        gui.div(className="pb-1")

    def lipsync_settings(self):
        with gui.div(className="pt-2 ps-1"):
            gui.file_uploader(
                """
                ###### 👩‍🦰 Input Face
                Upload a video/image with one human face. mp4, mov, png, jpg or gif preferred.
                """,
                key="input_face",
            )
            enum_selector(
                LipsyncModel,
                label="###### Lipsync Model",
                key="lipsync_model",
                use_selectbox=True,
            )
            gui.newline()

    def document_intelligence_settings(self):
        with gui.div(className="pt-2 ps-1"):
            document_intelligence_settings(
                title=f"{field_desc(self.RequestModel, 'document_model')}",
            )

    def render_usage_guide(self):
        youtube_video("4wGKQAGUm48")

    def render_settings(self):
        tts_provider = gui.session_state.get("tts_provider")
        if tts_provider:
            text_to_speech_settings(self, tts_provider)
            gui.write("---")

        lipsync_model = gui.session_state.get("lipsync_model")
        if lipsync_model and gui.session_state.get("input_face"):
            lipsync_settings(lipsync_model)
            gui.write("---")

        translation_model = gui.session_state.get(
            "translation_model", DEFAULT_TRANSLATION_MODEL
        )
        if (
            gui.session_state.get("user_language")
            and TranslationModels[translation_model].supports_glossary
        ):
            gui.markdown("##### 🔠 Translation Settings")
            enable_glossary = gui.checkbox(
                "📖 Add Glossary",
                value=bool(
                    gui.session_state.get("input_glossary_document")
                    or gui.session_state.get("output_glossary_document")
                ),
                help="[Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/advanced-settings#fine-tuned-language-understanding-with-custom-glossaries) about how to super-charge your agent's domain specific language understanding!",
            )
            if enable_glossary:
                gui.caption(
                    """
                    Provide a glossary to customize translation and improve accuracy of domain-specific terms.
                    If not specified or invalid, no glossary will be used. Read about the expected format [here](https://docs.google.com/document/d/1TwzAvFmFYekloRKql2PXNPIyqCbsHRL8ZtnWkzAYrh8/edit?usp=sharing).
                    """
                )
                gui.file_uploader(
                    f"##### {field_title_desc(self.RequestModel, 'input_glossary_document')}",
                    key="input_glossary_document",
                    accept=SUPPORTED_SPREADSHEET_TYPES,
                )
                gui.file_uploader(
                    f"##### {field_title_desc(self.RequestModel, 'output_glossary_document')}",
                    key="output_glossary_document",
                    accept=SUPPORTED_SPREADSHEET_TYPES,
                )
            else:
                gui.session_state["input_glossary_document"] = None
                gui.session_state["output_glossary_document"] = None
            gui.write("---")

        documents = gui.session_state.get("documents")
        if documents:
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

        gui.markdown(
            """
            #### Advanced Settings
            In general, you should not need to adjust these.
            """
        )

        if documents:
            query_instructions_widget()
            keyword_instructions_widget()
            gui.write("---")
            doc_search_advanced_settings()
            gui.write("---")

        gui.write("##### 🔠 Language Model Settings")
        language_model_settings(gui.session_state.get("selected_model"))

    def run_as_api_tab(self):
        elevenlabs_load_state(self)
        super().run_as_api_tab()

    def render_run_preview_output(self, state: dict):
        input_prompt = state.get("input_prompt") or state.get("raw_input_text")
        if input_prompt:
            with (
                gui.div(className="d-flex justify-content-end mb-1"),
                gui.div(
                    className="bg-light rounded-3 text-dark p-2",
                    style=dict(maxWidth="85%"),
                ),
            ):
                gui.write(
                    truncate_text_words(input_prompt, maxlen=200),
                    className="container-margin-reset",
                )

        output_video = state.get("output_video")
        output_text = state.get("output_text")
        output_audio = state.get("output_audio")
        if not (output_text or output_video or output_audio):
            return

        with gui.div(style=dict(width="85%"), className="pt-3"):
            if output_video:
                gui.video(output_video[0], autoplay=True)

            if output_audio:
                gui.audio(output_audio[0])

            if output_text:
                with (
                    gui.div(
                        className="border rounded-3 p-2",
                        style=dict(borderColor="#f0f0f0"),
                    ),
                    gui.styled("""
                        & {
                            max-height: 4.5em; /* ~3 lines with 1.5 line-height */
                            overflow: hidden;
                            display: -webkit-box;
                            -webkit-line-clamp: 3;
                            -webkit-box-orient: vertical;
                            line-height: 1.5;
                        }
                    """),
                ):
                    text = parse_bot_html(output_text[0])[1]
                    gui.write(text, className="container-margin-reset")

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
            # routers.bots_api imports VideoBotsPage; keep this DEBUG-only.
            from routers.bots_api import stream_create

            config["apiUrl"] = get_api_route_url(stream_create)

        gui.div(
            # fill the scrolling body area, not the viewport: the top bar sits above this,
            # so `100vh` would overflow by exactly the bar's height
            style=dict(height="100%", minHeight=0),
            id="gooey-embed",
        )
        # Owns the widget's teardown when this preview disappears or a different workflow
        # replaces it client-side.
        gui.component(
            "GooeyEmbedTeardown",
            embed_key=str(self.current_pr.published_run_id),
        )
        load_chat_widget_lib()
        gui.js(
            """
async function loadGooeyEmbed() {
    await window.waitUntilHydrated;
    let embedTarget = document.getElementById("gooey-embed");
    if (typeof GooeyEmbed === "undefined" || !embedTarget || embedTarget.children.length) {
        return;
    }
    let controller = {
        messages,
        onSendMessage: (payload) => {
            let btn = document.getElementById("onSendMessage");
            if (!btn) return;
            btn.value = JSON.stringify(payload);
            btn.click();
        },
        onNewConversation() {
          document.getElementById("onNewConversation").click();
        },
        fetchConversations: () => gui.fetchServerAPI("/__/agent/fetch-conversations", { run_url }),
    };
    GooeyEmbed.copilotPreviewControl = controller;
    GooeyEmbed.mount(config, controller);
}

const script = document.getElementById("gooey-embed-script");
if (script) script.onload = loadGooeyEmbed;
loadGooeyEmbed();
window.addEventListener("hydrated", loadGooeyEmbed);
// once the widget is already mounted, update the messages and branding to latest
if (typeof GooeyEmbed !== "undefined" && GooeyEmbed.copilotPreviewControl) {
    GooeyEmbed.copilotPreviewControl.setMessages?.(messages);
    GooeyEmbed.copilotPreviewControl.updateConfig?.({
        theme: config.theme,
        branding: config.branding,
        showHeader: config.showHeader,
    });
}
            """,
            config=config,
            messages=messages,
            run_url=str(self.request.url),
        )

    @cached_property
    def _has_whatsapp_integration(self) -> bool:
        return BotIntegration.objects.filter(
            published_run=self.current_pr,
            platform=Platform.WHATSAPP,
        ).exists()

    def _render_regenerate_button(self):
        pass

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

    def _top_bar_integrations(self) -> list[TopBarIntegration]:
        """v1's demo buttons, as chips in the top bar.

        They open a dialog rather than navigating, so each carries an action key instead of
        an href and comes back through the bar's menu key.
        """
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

    def _handle_top_bar_actions(self):
        super()._handle_top_bar_actions()

        picked = gui.session_state.pop(self.TOP_BAR_MENU_KEY, None)
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
        with gui.component(
            "RecipeWorkspaceTrigger",
            storage_key=self._workspace_storage_key(),
            initial_view=self.entry_tab_slug(self.get_tab_spec()),
            view=RecipeView.edit,
            state_key=self.CONFIG_PANE_KEY,
            state_value=pane,
            className="v2-about-meta-card",
        ):
            # icon over label, and no chevron: the whole card is the link, so an affordance
            # arrow only competed with the icon for the eye
            gui.html(
                f'<span class="v2-about-meta-icon">{icon}</span>'
                f'<span class="v2-about-meta-label">{html.escape(label)}</span>'
            )

    def _editor_wants_full_width(self) -> bool:
        """Deploy is a wide configuration surface that carries its own web preview, so
        pairing it with the chat preview leaves both cramped. It takes the full width
        instead, and the controls that would pair it back up go with it.
        """
        return gui.session_state.get(self.CONFIG_PANE_KEY) == ConfigPane.deploy

    def _render_split_tab(self):
        """Split is two columns, except where the open pane has claimed the row."""
        if self._editor_wants_full_width():
            # one column of 12 rather than no column at all, so the full-width pane keeps
            # the same gutters as the two-column layout. No submit row here to redirect on.
            self._render_solo_input_col()
            return
        super()._render_split_tab()

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
            PaneSpec(ConfigPane.deploy, "Deploy", self._render_deploy_panel),
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
