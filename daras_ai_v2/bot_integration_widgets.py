from django.core.exceptions import ValidationError
from django.db import transaction
from furl import furl

import gooey_ui as st
from app_users.models import AppUser
from bots.models import BotIntegration, BotIntegrationAnalysisRun
from daras_ai_v2 import settings
from daras_ai_v2.workflow_url_input import workflow_url_input
from recipes.BulkRunner import list_view_editor
from recipes.CompareLLM import CompareLLMPage


def general_integration_settings(bi: BotIntegration, current_user: AppUser):
    if st.session_state.get(f"_bi_reset_{bi.id}"):
        st.session_state[f"_bi_streaming_enabled_{bi.id}"] = (
            BotIntegration._meta.get_field("streaming_enabled").default
        )
        st.session_state[f"_bi_show_feedback_buttons_{bi.id}"] = (
            BotIntegration._meta.get_field("show_feedback_buttons").default
        )
        st.session_state["analysis_urls"] = []
        st.session_state.pop("--list-view:analysis_urls", None)

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

    st.write(
        """
        ##### 🧠 Analysis Scripts
        Analyze each incoming message and the copilot's response using a Gooey.AI /LLM workflow. Must return a JSON object.
        [Learn more](https://gooey.ai/docs/guides/build-your-ai-copilot/conversation-analysis).
        """
    )
    if "analysis_urls" not in st.session_state:
        st.session_state["analysis_urls"] = [
            (anal.published_run or anal.saved_run).get_app_url()
            for anal in bi.analysis_runs.all()
        ]

    input_analysis_runs = []

    def render_workflow_url_input(key: str, del_key: str | None, d: dict):
        with st.columns([3, 2])[0]:
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

    with st.center():
        with st.div():
            pressed_update = st.button("✅ Save")
            pressed_reset = st.button(
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
                st.error(str(e))
    st.write("---")


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
