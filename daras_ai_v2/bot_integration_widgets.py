from itertools import zip_longest
from textwrap import dedent

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from furl import furl

import gooey_gui as gui
from app_users.models import AppUser
from bots.models import BotIntegration, BotIntegrationAnalysisRun, Platform
from daras_ai_v2 import settings, icons
from daras_ai_v2.api_examples_widget import bot_api_example_generator
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.workflow_url_input import workflow_url_input
from recipes.BulkRunner import list_view_editor
from recipes.CompareLLM import CompareLLMPage
from routers.root import RecipeTabs, chat_route, chat_lib_route


def general_integration_settings(bi: BotIntegration, current_user: AppUser):
    if gui.session_state.get(f"_bi_reset_{bi.id}"):
        gui.session_state[f"_bi_streaming_enabled_{bi.id}"] = (
            BotIntegration._meta.get_field("streaming_enabled").default
        )
        gui.session_state[f"_bi_show_feedback_buttons_{bi.id}"] = (
            BotIntegration._meta.get_field("show_feedback_buttons").default
        )
        gui.session_state["analysis_urls"] = []
        gui.session_state.pop("--list-view:analysis_urls", None)

    if bi.platform != Platform.TWILIO:
        bi.streaming_enabled = gui.checkbox(
            "**📡 Streaming Enabled**",
            value=bi.streaming_enabled,
            key=f"_bi_streaming_enabled_{bi.id}",
        )
        gui.caption("Responses will be streamed to the user in real-time if enabled.")
        bi.show_feedback_buttons = gui.checkbox(
            "**👍🏾 👎🏽 Show Feedback Buttons**",
            value=bi.show_feedback_buttons,
            key=f"_bi_show_feedback_buttons_{bi.id}",
        )
        gui.caption(
            "Users can rate and provide feedback on every copilot response if enabled."
        )

    gui.write(
        """
        ##### 🧠 Analysis Scripts
        Analyze each incoming message and the copilot's response using a Gooey.AI /LLM workflow. Must return a JSON object.
        [Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/conversation-analysis).
        """
    )
    if "analysis_urls" not in gui.session_state:
        gui.session_state["analysis_urls"] = [
            (anal.published_run or anal.saved_run).get_app_url()
            for anal in bi.analysis_runs.all()
        ]

    if gui.session_state.get("analysis_urls"):
        from recipes.VideoBots import VideoBotsPage

        gui.anchor(
            "📊 View Results",
            str(
                furl(
                    VideoBotsPage.current_app_url(
                        RecipeTabs.integrations,
                        path_params=dict(integration_id=bi.api_integration_id()),
                    )
                )
                / "analysis/"
            ),
        )

    input_analysis_runs = []

    def render_workflow_url_input(key: str, del_key: str | None, d: dict):
        with gui.columns([3, 2])[0]:
            ret = workflow_url_input(
                page_cls=CompareLLMPage,
                key=key,
                internal_state=d,
                del_key=del_key,
                current_user=current_user,
            )
            if not ret:
                return
            page_cls, sr, pr = ret
            if pr and pr.saved_run_id == sr.id:
                input_analysis_runs.append(dict(saved_run=None, published_run=pr))
            else:
                input_analysis_runs.append(dict(saved_run=sr, published_run=None))

    list_view_editor(
        add_btn_label="➕ Add",
        key="analysis_urls",
        render_inputs=render_workflow_url_input,
        flatten_dict_key="url",
    )

    with gui.center():
        with gui.div():
            pressed_update = gui.button("✅ Save")
            pressed_reset = gui.button(
                "Reset", key=f"_bi_reset_{bi.id}", type="tertiary"
            )
    if pressed_update or pressed_reset:
        with transaction.atomic():
            try:
                bi.full_clean()
                bi.save()
                # save analysis runs
                input_analysis_runs = [
                    BotIntegrationAnalysisRun.objects.get_or_create(
                        bot_integration=bi, **data
                    )[0].id
                    for data in input_analysis_runs
                ]
                # delete any analysis runs that were removed
                bi.analysis_runs.all().exclude(id__in=input_analysis_runs).delete()
            except ValidationError as e:
                gui.error(str(e))
    gui.write("---")


def twilio_specific_settings(bi: BotIntegration):
    SETTINGS_FIELDS = ["twilio_use_missed_call", "twilio_initial_text", "twilio_initial_audio_url", "twilio_waiting_text", "twilio_waiting_audio_url"]  # fmt:skip
    if gui.session_state.get(f"_bi_reset_{bi.id}"):
        for field in SETTINGS_FIELDS:
            gui.session_state[f"_bi_{field}_{bi.id}"] = BotIntegration._meta.get_field(
                field
            ).default

    bi.twilio_initial_text = gui.text_area(
        "###### 📝 Initial Text (said at the beginning of each call)",
        value=bi.twilio_initial_text,
        key=f"_bi_twilio_initial_text_{bi.id}",
    )
    bi.twilio_initial_audio_url = (
        gui.file_uploader(
            "###### 🔊 Initial Audio (played at the beginning of each call)",
            accept=["audio/*"],
            key=f"_bi_twilio_initial_audio_url_{bi.id}",
        )
        or ""
    )
    bi.twilio_waiting_audio_url = (
        gui.file_uploader(
            "###### 🎵 Waiting Audio (played while waiting for a response -- Voice)",
            accept=["audio/*"],
            key=f"_bi_twilio_waiting_audio_url_{bi.id}",
        )
        or ""
    )
    bi.twilio_waiting_text = gui.text_area(
        "###### 📝 Waiting Text (texted while waiting for a response -- SMS)",
        key=f"_bi_twilio_waiting_text_{bi.id}",
    )
    bi.twilio_use_missed_call = gui.checkbox(
        "📞 Use Missed Call",
        value=bi.twilio_use_missed_call,
        key=f"_bi_twilio_use_missed_call_{bi.id}",
    )
    gui.caption(
        "When enabled, immediately hangs up incoming calls and calls back the user so they don't incur charges (depending on their carrier/plan)."
    )


def slack_specific_settings(bi: BotIntegration, default_name: str):
    if gui.session_state.get(f"_bi_reset_{bi.id}"):
        gui.session_state[f"_bi_name_{bi.id}"] = default_name
        gui.session_state[f"_bi_slack_read_receipt_msg_{bi.id}"] = (
            BotIntegration._meta.get_field("slack_read_receipt_msg").default
        )

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


def get_bot_test_link(bi: BotIntegration) -> str | None:
    if bi.wa_phone_number:
        return (
            furl("https://wa.me/", query_params={"text": "Hi"})
            / bi.wa_phone_number.as_e164
        ).tostr()
    elif bi.slack_team_id:
        return (
            furl("https://app.slack.com/client")
            / bi.slack_team_id
            / bi.slack_channel_id
        ).tostr()
    elif bi.ig_username:
        return (furl("http://instagram.com/") / bi.ig_username).tostr()
    elif bi.fb_page_name:
        return (furl("https://www.facebook.com/") / bi.fb_page_id).tostr()
    elif bi.platform == Platform.WEB:
        return get_app_route_url(
            chat_route,
            path_params=dict(
                integration_id=bi.api_integration_id(),
                integration_name=slugify(bi.name) or "untitled",
            ),
        )
    elif bi.twilio_phone_number:
        return str(furl("tel:") / bi.twilio_phone_number.as_e164)
    else:
        return None


def get_web_widget_embed_code(bi: BotIntegration) -> str:
    lib_src = get_app_route_url(
        chat_lib_route,
        path_params=dict(
            integration_id=bi.api_integration_id(),
            integration_name=slugify(bi.name) or "untitled",
        ),
    ).rstrip("/")
    return dedent(
        f"""
        <div id="gooey-embed"></div>
        <script async defer onload="GooeyEmbed.mount()" src="{lib_src}"></script>
        """
    ).strip()


def web_widget_config(bi: BotIntegration, user: AppUser | None):
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
            if gui.button(f"{icons.camera} Change Photo"):
                gui.session_state["--update-display-picture"] = True
                gui.rerun()
        bi.name = gui.text_input("###### Name", value=bi.name)
        bi.descripton = gui.text_area(
            "###### Description",
            value=bi.descripton,
        )
        scol1, scol2 = gui.columns(2)
        with scol1:
            bi.by_line = gui.text_input(
                "###### By Line",
                value=bi.by_line or (user and f"By {user.display_name}"),
            )
        with scol2:
            bi.website_url = gui.text_input(
                "###### Website Link",
                value=bi.website_url or (user and user.website_url),
            )

        gui.write("###### Conversation Starters")
        bi.conversation_starters = list(
            filter(
                None,
                [
                    gui.text_input("", key=f"--question-{i}", value=value)
                    for i, value in zip_longest(range(4), bi.conversation_starters)
                ],
            )
        )

        config = (
            dict(
                mode="inline",
                showSources=True,
                enablePhotoUpload=False,
                enableLipsyncVideo=False,
                enableAudioMessage=True,
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
                "Allow Photo Upload", value=config["enablePhotoUpload"]
            )
        with scol2:
            config["enableAudioMessage"] = gui.checkbox(
                "Enable Audio Message", value=config["enableAudioMessage"]
            )
            config["enableLipsyncVideo"] = gui.checkbox(
                "Enable Lipsync Video", value=config["enableLipsyncVideo"]
            )
            # config["branding"]["showPoweredByGooey"] = gui.checkbox(
            #     "Show Powered By Gooey", value=config["branding"]["showPoweredByGooey"]
            # )

        with gui.expander("Embed Settings"):
            gui.caption(
                "These settings will take effect when you embed the widget on your website."
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

        # remove defaults
        bi.web_config_extras = config

        with gui.div(className="d-flex justify-content-end"):
            if gui.button(
                f"{icons.save} Update Web Preview",
                type="primary",
                className="align-right",
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
                <div id="gooey-embed" style="border: 1px solid #eee; height: 80vh"></div>
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
                config=bi.get_web_widget_config() | dict(mode="inline"),
            )
        else:
            bot_api_example_generator(bi.api_integration_id())
