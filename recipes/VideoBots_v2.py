import html
import json
from enum import Enum
from functools import cached_property

import gooey_gui as gui
from ai_models.models import AIModelSpec
from bots.models import BotIntegration, Platform
from daras_ai_v2 import icons, settings
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
from daras_ai_v2.fastapi_tricks import get_api_route_url
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.integrations_tab import render_integrations_tab
from daras_ai_v2.language_model_settings_widgets import (
    language_model_selector,
)
from daras_ai_v2.tab_spec import (
    PaneSpec,
    SingleLayout,
    SplitLayout,
    SurfaceId,
    TabSpec,
)
from daras_ai_v2.web_widget_embed import (
    get_chat_widget_messages,
    load_chat_widget_lib,
)
from functions.base_llm_tool import render_called_functions
from functions.models import FunctionTrigger
from gooey_gui.types.recipe_top_bar_props import (
    MenuIntent,
    SubmitTarget,
    TopBarIntegration,
)
from gooey_gui.types.recipe_workspace_props import (
    RecipeWorkspaceTriggerProps,
    SessionStateUpdate,
)

from recipes.VideoBots import VideoBotsPage
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
   it outranks emotion's own single-class rule without `!important`. */
& .gui-input-select [class*="-control"] {
    border-radius: 10px;
}
"""


# `(str, Enum)` rather than `enum.StrEnum`: this runs on 3.10, where StrEnum does not exist.
# Matching `BulkRunnerRunState` in gooey_gui/types/bulk_progress_props.py.
class ConfigPane(str, Enum):
    """Stable ids for the working column's panes. Session state and the About cards' deep
    links carry these, so they must not change; the labels in `_config_panes()` may."""

    llm_instructions = "llm-instructions"
    knowledge = "knowledge"
    tools = "tools"
    settings = "settings"
    debug = "debug"


class VideoBotsPageV2(BasePage, VideoBotsPage):
    """The agent recipe in layout v2.

    Base order matters: `BasePage` is the v2 shell and must come first, or v1's `render`
    wins. `VideoBotsPage` supplies the models, the pipeline and the cost maths.
    """

    @classmethod
    def get_runner_page_cls(cls):
        return VideoBotsPage

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
        # Fill the remaining preview area below the top bar.
        gui.component(
            "GooeyEmbedPreview",
            config=config,
            messages=messages,
            run_url=str(self.request.url),
            # Sized by the flex column in `_render_output_col`, not by `height: 100%`: the
            # widget shares that column with the failure box, the cancelled notice and the
            # run spinner, and a percentage height would claim the whole column regardless of
            # what is above it. `minHeight: 0` so it can shrink when one of them appears.
            className="flex-grow-1",
            style=dict(minHeight=0),
        )

    @cached_property
    def _has_whatsapp_integration(self) -> bool:
        return BotIntegration.objects.filter(
            published_run=self.current_pr,
            platform=Platform.WHATSAPP,
        ).exists()

    DEMO_ACTION_PREFIX = "demo:"

    def _top_bar_integrations(self) -> list[TopBarIntegration]:
        """Demo buttons as top bar chips. They open a dialog rather than navigating, so each
        carries an action key instead of an href."""
        from widgets.demo_button import get_demo_bots

        integrations = []
        for bi_id, platform_id in get_demo_bots(self.current_pr):
            platform = Platform(platform_id)
            integrations.append(
                TopBarIntegration(
                    key=f"{self.DEMO_ACTION_PREFIX}{bi_id}",
                    label=f"Try in {platform.get_title()}",
                    icon_html=platform.get_icon(),
                    target=SubmitTarget(
                        intent=MenuIntent(item_key=f"{self.DEMO_ACTION_PREFIX}{bi_id}")
                    ),
                    color=platform.get_demo_button_color() or None,
                )
            )
        return integrations

    def _handle_menu_pick(self, picked: str | None):
        """The demo chips, which come back through the same menu key the title menu uses."""
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

    def get_tab_spec(self) -> list[TabSpec]:
        """The agent tab set. Deploy is absent - its body is reached through the
        `/integrations/` url via `render_selected_tab()`."""
        if self.is_unowned_example():
            return self.get_viewer_tab_spec()
        return [
            TabSpec(
                key="about",
                label="About",
                icon_html=icons.info,
                layout=SplitLayout(
                    primary=SurfaceId.about,
                    secondary=SurfaceId.preview,
                ),
            ),
            TabSpec(
                key="edit",
                label="Edit",
                icon_html=icons.edit,
                layout=SingleLayout(surface=SurfaceId.editor),
            ),
            TabSpec(
                key="preview",
                label="Preview",
                icon_html=icons.preview,
                layout=SingleLayout(surface=SurfaceId.preview),
            ),
            TabSpec(
                key="split",
                label="Split",
                icon_html=icons.split,
                layout=SplitLayout(
                    primary=SurfaceId.editor,
                    secondary=SurfaceId.preview,
                ),
                desktop_only=True,
            ),
        ]

    CONFIG_PANE_KEY = "--edit-subtab"

    def _render_about_meta(self):
        """How this agent is put together. Each card links into the config pane that owns
        the setting."""
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
                layout=SingleLayout(surface=SurfaceId.editor),
                state_update=SessionStateUpdate(
                    key=self.CONFIG_PANE_KEY,
                    value=pane.value,
                ),
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
        """The working column's panes, in strip order. Each composes existing widgets."""
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
        """The working column, shared by Edit and Split. Overridden here rather than per
        tab, so both get the pane strip without duplicating the layout."""
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
        """Variables beside the prompt that references them: a count on the button, the
        editing in a dialog. The count reads the prompt via `variable_names()`, so it is
        right before the editor has ever been opened."""
        ref = gui.use_alert_dialog(key="variables-modal")
        # "(0)" reads as a broken counter rather than an empty list, so it is left off
        count = len(self.variable_names())
        if gui.button(
            f"{icons.variables} Variables" + (f" ({count})" if count else ""),
            type="tertiary",
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
        """Model selector pinned on top, editor filling the height that is left."""
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
        # The model selector is on another pane, so read its session-state value.
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
        """Render deployment settings for the integrations route."""
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
