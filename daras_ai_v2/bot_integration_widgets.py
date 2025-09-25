import json
from itertools import zip_longest
from textwrap import dedent

import gooey_gui as gui
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from furl import furl

from app_users.models import AppUser
from bots.models import BotIntegration, BotIntegrationAnalysisRun, Platform
from daras_ai_v2 import icons, settings
from daras_ai_v2.api_examples_widget import bot_api_example_generator
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.functional import flatten
from daras_ai_v2.workflow_url_input import workflow_url_input
from functions.inbuilt_tools import FeedbackCollectionLLMTool
from recipes.BulkRunner import list_view_editor
from recipes.CompareLLM import CompareLLMPage
from routers.root import chat_lib_route
from widgets.demo_button import render_demo_button_settings
from workspaces.models import Workspace


def integrations_welcome_screen(title: str):
    with gui.center():
        gui.markdown(f"#### {title}")

    col1, col2, col3 = gui.columns(
        3,
        column_props=dict(
            style=dict(
                display="flex",
                flexDirection="column",
                alignItems="center",
                textAlign="center",
                maxWidth="300px",
            ),
        ),
        style={"justifyContent": "center"},
    )
    with col1:
        gui.html("🏃‍♀️", style={"fontSize": "4rem"})
        gui.markdown(
            """
            1. Fork & Save your Run
            """
        )
        gui.caption("Make changes, Submit & Save your perfect workflow")
    with col2:
        gui.image(icons.integrations_img, alt="Integrations", style={"height": "5rem"})
        gui.markdown("2. Connect to Slack, Whatsapp or your App")
        gui.caption("Or Facebook, Instagram and the web. Wherever your users chat.")
    with col3:
        gui.html("📈", style={"fontSize": "4rem"})
        gui.markdown("3. Test, Analyze & Iterate")
        gui.caption("Analyze your usage. Update your Saved Run to test changes.")


def general_integration_settings(
    user: AppUser, workspace: Workspace, bi: BotIntegration, has_test_link: bool
):
    if has_test_link:
        render_demo_button_settings(workspace=workspace, user=user, bi=bi)

    if bi.platform == Platform.SLACK:
        slack_specific_settings(bi)

    if bi.platform == Platform.TWILIO:
        twilio_specific_settings(bi)
    else:
        col1, col2, _ = gui.columns([1, 1, 2])
        with col1:
            bi.streaming_enabled = gui.checkbox(
                "**📡 Streaming Enabled**",
                value=bi.streaming_enabled,
                key=f"_bi_streaming_enabled_{bi.id}",
                help="Responses will be streamed to the user in real-time if enabled.",
            )
        with col2:
            bi.show_feedback_buttons = gui.checkbox(
                "**👍🏾 👎🏽 Show Feedback Buttons**",
                value=bi.show_feedback_buttons,
                key=f"_bi_show_feedback_buttons_{bi.id}",
                help="Users can rate and provide feedback on every copilot response if enabled.",
            )

        # Show detailed feedback option only if feedback buttons are enabled
        if bi.show_feedback_buttons:
            with gui.div(className="d-flex align-items-center gap-3"):
                bi.ask_detailed_feedback = gui.checkbox(
                    "**💬 Ask for Detailed Feedback**",
                    value=bi.ask_detailed_feedback,
                    key=f"_bi_ask_detailed_feedback_{bi.id}",
                    help=(
                        "When users give a thumbs down, ask them to explain what was wrong and how it could be improved. "
                        "Make sure to use our suggested prompt in your copilot to make this work well."
                    ),
                )
                copy_to_clipboard_button(
                    label=f"{icons.copy_solid} Copy Prompt",
                    value=FeedbackCollectionLLMTool.system_prompt,
                    type="link",
                )

    input_analysis_runs = analysis_runs_list_view(user, bi)

    if gui.button(
        f"{icons.save} Save Settings",
        type="primary",
        style=dict(marginLeft="-2px", marginTop="8px"),
    ):
        with transaction.atomic():
            try:
                bi.full_clean()
                bi.save()
                save_analysis_runs_for_integration(bi, input_analysis_runs)
            except ValidationError as e:
                gui.error(str(e))


def analysis_runs_list_view(
    user: AppUser,
    bi: BotIntegration,
    key: str = "analysis_urls",
    default_analysis_url: str = "https://gooey.ai/compare-large-language-models/default-copilot-analysis-script-8qqg3xb84ddc/",
) -> list[dict]:
    with gui.div(className="d-flex align-items-center gap-3 mb-2"):
        gui.write(
            "##### <i class='fa-solid fa-brain'></i> Analysis Workflows",
            unsafe_allow_html=True,
            help=(
                "Analyze each incoming message and the copilot's response using a Gooey.AI /LLM workflow. "
                "Must return a JSON object with a consistent schema. [Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/conversation-analysis)."
            ),
        )
        if gui.button(
            f"{icons.add} Add",
            type="tertiary",
            className="p-1 mb-2",
            key=key + ":add-workflow",
        ):
            list_items = gui.session_state.setdefault(f"--list-view:{key}", [])
            list_items.append({"url": default_analysis_url})

    if key not in gui.session_state:
        gui.session_state[key] = [
            (anal.published_run or anal.saved_run).get_app_url()
            for anal in bi.analysis_runs.all()
        ]

    input_analysis_runs = []

    def render_workflow_url_input(key: str, del_key: str | None, d: dict):
        with gui.columns([3, 2])[0]:
            ret = workflow_url_input(
                page_cls=CompareLLMPage,
                key=key,
                internal_state=d,
                del_key=del_key,
                current_user=user,
            )
            if not ret:
                return
            page_cls, sr, pr = ret
            if pr and pr.saved_run_id == sr.id:
                input_analysis_runs.append(dict(saved_run=None, published_run=pr))
            else:
                input_analysis_runs.append(dict(saved_run=sr, published_run=None))

    list_view_editor(
        key=key,
        render_inputs=render_workflow_url_input,
        flatten_dict_key="url",
    )

    return input_analysis_runs


def save_analysis_runs_for_integration(
    bi: BotIntegration, input_analysis_runs: list[dict]
):
    """
    Save analysis runs for the given BotIntegration and clean up removed runs.
    """
    input_analysis_run_ids = [
        BotIntegrationAnalysisRun.objects.get_or_create(bot_integration=bi, **data)[
            0
        ].id
        for data in input_analysis_runs
    ]
    # delete any analysis runs that were removed
    bi.analysis_runs.all().exclude(id__in=input_analysis_run_ids).delete()


def twilio_specific_settings(bi: BotIntegration):
    SETTINGS_FIELDS = ["twilio_use_missed_call", "twilio_initial_text", "twilio_initial_audio_url", "twilio_waiting_text", "twilio_waiting_audio_url", "twilio_fresh_conversation_per_call"]  # fmt:skip

    bi.twilio_initial_text = gui.text_area(
        "###### 📝 Initial Text (said at the beginning of each call)",
        value=bi.twilio_initial_text,
        key=f"_bi_twilio_initial_text_{bi.id}",
    )
    bi.twilio_initial_audio_url = (
        gui.file_uploader(
            "###### 🔊 Initial Audio (played at the beginning of each call)",
            accept=["audio/*"],
            value=bi.twilio_initial_audio_url,
            key=f"_bi_twilio_initial_audio_url_{bi.id}",
        )
        or ""
    )
    bi.twilio_waiting_audio_url = (
        gui.file_uploader(
            "###### 🎵 Waiting Audio (played while waiting for a response -- Voice)",
            accept=["audio/*"],
            value=bi.twilio_waiting_audio_url,
            key=f"_bi_twilio_waiting_audio_url_{bi.id}",
        )
        or ""
    )
    bi.twilio_waiting_text = gui.text_area(
        "###### 📝 Waiting Text (texted while waiting for a response -- SMS)",
        value=bi.twilio_waiting_text,
        key=f"_bi_twilio_waiting_text_{bi.id}",
    )

    bi.twilio_use_missed_call = gui.checkbox(
        "📞 Use Missed Call",
        value=bi.twilio_use_missed_call,
        key=f"_bi_twilio_use_missed_call_{bi.id}",
        disabled=bi.extension_number,
    )

    if bi.extension_number:
        gui.caption(
            f"[Upgrade]({settings.PRICING_DETAILS_URL}) for missed call support."
        )

    gui.caption(
        "When enabled, immediately hangs up incoming calls and calls back the user so they don't incur charges (depending on their carrier/plan)."
    )

    bi.twilio_fresh_conversation_per_call = gui.checkbox(
        "🔄 Fresh Conversation History for Each Call",
        value=bi.twilio_fresh_conversation_per_call,
        key=f"_bi_twilio_fresh_conversation_per_call_{bi.id}",
    )


def slack_specific_settings(bi: BotIntegration):
    bi.slack_read_receipt_msg = gui.text_input(
        """
            ##### ✅ Read Receipt
            This message is sent immediately after recieving a user message and replaced with the copilot's response once it's ready.
            (leave blank to disable)
            """,
        placeholder=bi.slack_read_receipt_msg,
        value=bi.slack_read_receipt_msg,
        key=f"_bi_slack_read_receipt_msg_{bi.id}",
    )
    bi.name = gui.text_input(
        """
            ##### 🪪 Channel Specific Bot Name
            This is the name the bot will post as in this specific channel (to be displayed in Slack)
            """,
        placeholder=bi.name,
        value=bi.name,
        key=f"_bi_name_{bi.id}",
    )
    gui.caption("Enable streaming messages to Slack in real-time.")


def broadcast_input(bi: BotIntegration):
    from bots.tasks import send_broadcast_msgs_chunked
    from recipes.VideoBots import VideoBotsPage

    key = f"__broadcast_msg_{bi.id}"
    api_docs_url = (
        furl(
            settings.API_BASE_URL,
            fragment_path=f"operation/{VideoBotsPage.slug_versions[0]}__broadcast",
        )
        / "docs"
    )
    text = gui.text_area(
        f"""
        ###### Broadcast Message 📢
        Broadcast a message to all users of this integration using this bot account.  \\
        You can also do this via the [API]({api_docs_url}) which allows filtering by phone number and more!
        """,
        key=key + ":text",
        placeholder="Type your message here...",
    )
    audio = gui.file_uploader(
        "**🎤 Audio**",
        key=key + ":audio",
        help="Attach a video to this message.",
        optional=True,
        accept=["audio/*"],
    )
    video = None
    documents = None
    medium = "Voice Call"
    if bi.platform == Platform.TWILIO:
        medium = gui.selectbox(
            "###### 📱 Medium",
            ["Voice Call", "SMS/MMS"],
            key=key + ":medium",
        )
    else:
        video = gui.file_uploader(
            "**🎥 Video**",
            key=key + ":video",
            help="Attach a video to this message.",
            optional=True,
            accept=["video/*"],
        )
        documents = gui.file_uploader(
            "**📄 Documents**",
            key=key + ":documents",
            help="Attach documents to this message.",
            accept_multiple_files=True,
            optional=True,
        )

    should_confirm_key = key + ":should_confirm"
    confirmed_send_btn = key + ":confirmed_send"
    if gui.button("📤 Send Broadcast", style=dict(height="3.2rem"), key=key + ":send"):
        gui.session_state[should_confirm_key] = True
    if not gui.session_state.get(should_confirm_key):
        return

    convos = bi.conversations.all()
    if gui.session_state.get(confirmed_send_btn):
        gui.success("Started sending broadcast!")
        gui.session_state.pop(confirmed_send_btn)
        gui.session_state.pop(should_confirm_key)
        send_broadcast_msgs_chunked(
            text=text,
            audio=audio,
            video=video,
            documents=documents,
            bi=bi,
            convo_qs=convos,
            medium=medium,
        )
    else:
        if not convos.exists():
            gui.error("No users have interacted with this bot yet.", icon="⚠️")
            return
        gui.write(
            f"Are you sure? This will send a message to all {convos.count()} users that have ever interacted with this bot.\n"
        )
        gui.button("✅ Yes, Send", key=confirmed_send_btn)


def get_web_widget_embed_code(bi: BotIntegration, *, config: dict = None) -> str:
    lib_src = get_app_route_url(
        chat_lib_route,
        path_params=dict(
            integration_id=bi.api_integration_id(),
            integration_name=slugify(bi.name) or "untitled",
        ),
    ).rstrip("/")
    if config is None:
        config = {}
    return dedent(
        """
        <div id="gooey-embed"></div>
        <script>
            function onLoadGooeyEmbed() {
                GooeyEmbed.mount(%(config_json)s);
            }
        </script>
        <script async defer onload="onLoadGooeyEmbed()" src="%(lib_src)s"></script>
        """
        % dict(config_json=json.dumps(config), lib_src=lib_src)
    ).strip()


def web_widget_config(bi: BotIntegration, user: AppUser | None, hostname: str | None):
    with gui.div(style={"width": "100%", "textAlign": "left"}):
        col1, col2 = gui.columns(2)
    with col1:
        if gui.session_state.get("--update-display-picture"):
            display_pic = gui.file_uploader(
                label="###### Display Picture",
                accept=["image/*"],
            )
            if display_pic:
                bi.photo_url = display_pic
        else:
            gencol1, gencol2 = gui.columns(2)
            with gencol1:
                if gui.button(f"{icons.camera} Change Photo"):
                    gui.session_state["--update-display-picture"] = True
                    gui.rerun()
            with gencol2:
                integration_details_generator(bi, user)

        bi.name = gui.text_input(
            "###### Name",
            key=f"_bi_name_{bi.id}",
            value=bi.name,
        )
        bi.descripton = gui.text_area(
            "###### Description",
            key=f"_bi_descripton_{bi.id}",
            value=bi.descripton,
        )
        scol1, scol2 = gui.columns(2)
        with scol1:
            bi.by_line = gui.text_input(
                "###### By Line",
                key=f"_bi_by_line_{bi.id}",
                value=bi.by_line or (user and f"By {user.display_name}"),
            )
        with scol2:
            bi.website_url = gui.text_input(
                "###### Website Link",
                key=f"_bi_website_url_{bi.id}",
                value=bi.website_url,
            )

        gui.write("###### Conversation Starters")
        bi.conversation_starters = list(
            filter(
                None,
                [
                    gui.text_input(
                        "", key=f"_bi_convo_starter_{bi.id}_{i}", value=value
                    )
                    for i, value in zip_longest(range(4), bi.conversation_starters)
                ],
            )
        )

        config = (
            dict(
                mode="inline",
                showSources=True,
                enablePhotoUpload=False,
                autoPlayResponses=True,
                enableAudioMessage=True,
                enableConversations=True,
                enableSourcePreview=True,
                branding=(
                    dict(showPoweredByGooey=True)
                    | bi.web_config_extras.get("branding", {})
                ),
            )
            | bi.web_config_extras
        )

        scol1, scol2 = gui.columns(2)
        with scol1:
            config["showSources"] = gui.checkbox(
                "Show Sources", value=config["showSources"]
            )
            config["enablePhotoUpload"] = gui.checkbox(
                "Allow Photo/File Upload", value=config["enablePhotoUpload"]
            )
            config["enableConversations"] = gui.checkbox(
                'Show "New Chat"', value=config["enableConversations"]
            )
        with scol2:
            config["enableAudioMessage"] = gui.checkbox(
                "Enable Audio Message", value=config["enableAudioMessage"]
            )
            config["autoPlayResponses"] = gui.checkbox(
                "Auto-play responses", value=config["autoPlayResponses"]
            )
            config["enableSourcePreview"] = gui.checkbox(
                "Preview Links & Sources", value=config["enableSourcePreview"]
            )

        with gui.expander("Embed Settings"):
            gui.caption(
                'These settings will take effect when you embed the widget on your website. Press "Update Web Preview" below after making any changes.'
            )
            scol1, scol2 = gui.columns(2)
            with scol1:
                config["mode"] = gui.selectbox(
                    "###### Mode",
                    ["popup", "inline", "fullscreen"],
                    value=config["mode"],
                    format_func=lambda x: x.capitalize(),
                )
                if config["mode"] == "popup":
                    config["branding"]["fabLabel"] = gui.text_input(
                        "###### Label",
                        value=config["branding"].get("fabLabel", "Help"),
                    )
                else:
                    config["branding"].pop("fabLabel", None)
                embed_code = get_web_widget_embed_code(bi)
                copy_to_clipboard_button(
                    f"{icons.code} Copy Embed Code",
                    value=embed_code,
                    type="secondary",
                )

        # remove defaults
        bi.web_config_extras = config

        if gui.button(
            f"{icons.save} Update Web Preview",
            type="primary",
            style=dict(marginLeft="-2px", marginTop="8px"),
        ):
            bi.save()
            gui.rerun()
    with col2:
        with gui.center(), gui.div():
            web_preview_tab = f"{icons.chat} Web Preview"
            api_tab = f"{icons.api} API"
            selected = gui.horizontal_radio("", [web_preview_tab, api_tab])
        if selected == web_preview_tab:
            gui.html(
                # language=html
                f"""
                <div id="gooey-embed" class="border rounded p-1" style="height:80vh"></div>
                <script id="gooey-embed-script" src="{settings.WEB_WIDGET_LIB}"></script>
                """
            )
            gui.js(
                # language=javascript
                """
                async function loadGooeyEmbed() {
                    await window.waitUntilHydrated;
                    if (typeof GooeyEmbed === 'undefined') return;
                    GooeyEmbed.unmount();
                    GooeyEmbed.mount(config);
                }
                const script = document.getElementById("gooey-embed-script");
                if (script) script.onload = loadGooeyEmbed;
                loadGooeyEmbed();
                """,
                config=bi.get_web_widget_config(hostname) | dict(mode="inline"),
            )
        else:
            bot_api_example_generator(bi.api_integration_id())


def integration_details_generator(bi: BotIntegration, user: AppUser | None):
    from bots.tasks import fill_req_vars_from_state

    if gui.session_state.get("details_generated_once"):
        return

    if gui.session_state.pop("generate_details_btn", None):
        llm_gen_pr = CompareLLMPage.get_pr_from_example_id(
            example_id=settings.INTEGRATION_DETAILS_GENERATOR_EXAMPLE_ID
        )
        variables = llm_gen_pr.saved_run.state.get("variables") or {}
        fill_req_vars_from_state(bi.get_active_saved_run().state, variables)
        variables |= dict(bi_name=bi.name)

        result, sr = llm_gen_pr.submit_api_call(
            workspace=bi.workspace,
            current_user=user,
            request_body=dict(variables=variables),
        )
        sr.wait_for_celery_result(result)
        # if failed, show error and abort
        if sr.error_msg:
            gui.error(sr.error_msg)
            return

        bi.website_url = bi.website_url or (user and user.website_url)
        for text in flatten(sr.state["output_text"].values()):
            output = json.loads(text)
            gui.session_state[f"_bi_descripton_{bi.id}"] = (
                output.get("description") or ""
            )
            bi.conversation_starters = output.get("conversation_starters") or []
            prev_keys = {
                k
                for k in gui.session_state.keys()
                if k.startswith("_bi_convo_starter_")
            }
            for k in prev_keys:
                gui.session_state.pop(k, None)
            gui.session_state["details_generated_once"] = True
            return

    gui.button(
        f"{icons.sparkles} Improve",
        style=dict(float="right"),
        type="tertiary",
        key="generate_details_btn",
    )
