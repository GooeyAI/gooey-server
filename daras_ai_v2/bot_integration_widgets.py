from django.core.exceptions import ValidationError
from furl import furl

import gooey_ui as st
from bots.models import BotIntegration, Platform
from bots.models import Workflow
from daras_ai_v2 import settings
from daras_ai_v2.asr import (
    google_translate_language_selector,
)
from daras_ai_v2.field_render import field_title_desc
from recipes.BulkRunner import url_to_runs


def general_integration_settings(bi: BotIntegration):
    from recipes.VideoBots import VideoBotsPage

    if st.session_state.get(f"_bi_reset_{bi.id}"):
        st.session_state[f"_bi_user_language_{bi.id}"] = BotIntegration._meta.get_field(
            "user_language"
        ).default
        st.session_state[f"_bi_show_feedback_buttons_{bi.id}"] = (
            BotIntegration._meta.get_field("show_feedback_buttons").default
        )
        st.session_state[f"_bi_analysis_url_{bi.id}"] = None

    bi.show_feedback_buttons = st.checkbox(
        "**👍🏾 👎🏽 Show Feedback Buttons**",
        value=bi.show_feedback_buttons,
        key=f"_bi_show_feedback_buttons_{bi.id}",
    )
    st.caption(
        "Users can rate and provide feedback on every copilot response if enabled."
    )

    bi.user_language = (
        google_translate_language_selector(
            f"""
##### {field_title_desc(VideoBotsPage.RequestModel, 'user_language')} \\
This will also help better understand incoming audio messages by automatically choosing the best [Speech](https://gooey.ai/speech/) model.
            """,
            default_value=bi.user_language,
            allow_none=False,
            key=f"_bi_user_language_{bi.id}",
        )
        or "en"
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
        ##### Broadcast Message
        Broadcast a message to all users of this integration using this bot account.  \\
        You can also do this via the [API]({api_docs_url}).
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
    if st.button("📢 Send Broadcast", style=dict(height="3.2rem"), key=key + ":send"):
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


def render_bot_test_link(bi: BotIntegration):
    if bi.wa_phone_number:
        test_link = (
            furl("https://wa.me/", query_params={"text": "Hi"})
            / bi.wa_phone_number.as_e164
        )
    elif bi.slack_team_id:
        test_link = (
            furl("https://app.slack.com/client")
            / bi.slack_team_id
            / bi.slack_channel_id
        )
    else:
        return
    st.html(
        f"""
        <a class="btn btn-theme btn-tertiary d-inline-block" target="blank" href="{test_link}">📱 Test</a>
        """
    )
