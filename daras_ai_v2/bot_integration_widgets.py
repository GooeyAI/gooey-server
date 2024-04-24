from django.core.exceptions import ValidationError
from furl import furl

import gooey_ui as st
from bots.models import BotIntegration
from bots.models import Workflow
from daras_ai_v2 import settings
from recipes.BulkRunner import url_to_runs


def general_integration_settings(bi: BotIntegration):
    if st.session_state.get(f"_bi_reset_{bi.id}"):
        st.session_state[f"_bi_streaming_enabled_{bi.id}"] = (
            BotIntegration._meta.get_field("streaming_enabled").default
        )
        st.session_state[f"_bi_show_feedback_buttons_{bi.id}"] = (
            BotIntegration._meta.get_field("show_feedback_buttons").default
        )
        st.session_state[f"_bi_analysis_url_{bi.id}"] = None

    bi.streaming_enabled = st.checkbox(
        "**📡 Streaming Enabled**",
        value=bi.streaming_enabled,
        key=f"_bi_streaming_enabled_{bi.id}",
    )
    st.caption("Responses will be streamed to the user in real-time if enabled.")
    bi.show_feedback_buttons = st.checkbox(
        "**👍🏾 👎🏽 Show Feedback Buttons**",
        value=bi.show_feedback_buttons,
        key=f"_bi_show_feedback_buttons_{bi.id}",
    )
    st.caption(
        "Users can rate and provide feedback on every copilot response if enabled."
    )

    st.caption(
        "Please note that this language is distinct from the one provided in the workflow settings. Hence, this allows you to integrate the same bot in many languages."
    )

    analysis_url = st.text_input(
        """
        ##### 🧠 Analysis Run URL
        Analyze each incoming message and the copilot's response using a Gooey.AI /LLM workflow url. Leave blank to disable. 
        [Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/conversation-analysis).
        """,
        value=bi.analysis_run and bi.analysis_run.get_app_url(),
        key=f"_bi_analysis_url_{bi.id}",
    )
    if analysis_url:
        try:
            page_cls, bi.analysis_run, _ = url_to_runs(analysis_url)
            assert page_cls.workflow in [
                Workflow.COMPARE_LLM,
                Workflow.VIDEO_BOTS,
                Workflow.GOOGLE_GPT,
                Workflow.DOC_SEARCH,
            ], "We only support Compare LLM, Copilot, Google GPT and Doc Search workflows for analysis."
        except Exception as e:
            bi.analysis_run = None
            st.error(repr(e))
    else:
        bi.analysis_run = None

    pressed_update = st.button("Update")
    pressed_reset = st.button("Reset", key=f"_bi_reset_{bi.id}", type="tertiary")
    if pressed_update or pressed_reset:
        try:
            bi.full_clean()
            bi.save()
        except ValidationError as e:
            st.error(str(e))


def slack_specific_settings(bi: BotIntegration, default_name: str):
    if st.session_state.get(f"_bi_reset_{bi.id}"):
        st.session_state[f"_bi_name_{bi.id}"] = default_name
        st.session_state[f"_bi_slack_read_receipt_msg_{bi.id}"] = (
            BotIntegration._meta.get_field("slack_read_receipt_msg").default
        )

    bi.slack_read_receipt_msg = st.text_input(
        """
            ##### ✅ Read Receipt
            This message is sent immediately after recieving a user message and replaced with the copilot's response once it's ready.
            (leave blank to disable)
            """,
        placeholder=bi.slack_read_receipt_msg,
        value=bi.slack_read_receipt_msg,
        key=f"_bi_slack_read_receipt_msg_{bi.id}",
    )
    bi.name = st.text_input(
        """
            ##### 🪪 Channel Specific Bot Name
            This is the name the bot will post as in this specific channel (to be displayed in Slack)
            """,
        placeholder=bi.name,
        value=bi.name,
        key=f"_bi_name_{bi.id}",
    )
    st.caption("Enable streaming messages to Slack in real-time.")


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
    text = st.text_area(
        f"""
        ###### Broadcast Message 📢
        Broadcast a message to all users of this integration using this bot account.  \\
        You can also do this via the [API]({api_docs_url}) which allows filtering by phone number and more!
        """,
        key=key + ":text",
        placeholder="Type your message here...",
    )
    audio = st.file_uploader(
        "**🎤 Audio**",
        key=key + ":audio",
        help="Attach a video to this message.",
        optional=True,
        accept=["audio/*"],
    )
    video = st.file_uploader(
        "**🎥 Video**",
        key=key + ":video",
        help="Attach a video to this message.",
        optional=True,
        accept=["video/*"],
    )
    documents = st.file_uploader(
        "**📄 Documents**",
        key=key + ":documents",
        help="Attach documents to this message.",
        accept_multiple_files=True,
        optional=True,
    )

    should_confirm_key = key + ":should_confirm"
    confirmed_send_btn = key + ":confirmed_send"
    if st.button("📤 Send Broadcast", style=dict(height="3.2rem"), key=key + ":send"):
        st.session_state[should_confirm_key] = True
    if not st.session_state.get(should_confirm_key):
        return

    convos = bi.conversations.all()
    if st.session_state.get(confirmed_send_btn):
        st.success("Started sending broadcast!")
        st.session_state.pop(confirmed_send_btn)
        st.session_state.pop(should_confirm_key)
        send_broadcast_msgs_chunked(
            text=text,
            audio=audio,
            video=video,
            documents=documents,
            bi=bi,
            convo_qs=convos,
        )
    else:
        if not convos.exists():
            st.error("No users have interacted with this bot yet.", icon="⚠️")
            return
        st.write(
            f"Are you sure? This will send a message to all {convos.count()} users that have ever interacted with this bot.\n"
        )
        st.button("✅ Yes, Send", key=confirmed_send_btn)


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
        return (furl("https://www.facebook.com/") / bi.fb_page_name).tostr()
    else:
        return None
