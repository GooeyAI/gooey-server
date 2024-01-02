from daras_ai_v2.base import BasePage, MenuTabs
import gooey_ui as st
from furl import furl

from app_users.models import AppUser

from bots.models import (
    Workflow,
    Platform,
    BotIntegration,
    Conversation,
    Message,
    Feedback,
    ConversationQuerySet,
    FeedbackQuerySet,
    MessageQuerySet,
)
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import plotly.graph_objects as go
import base64
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
)
from recipes.VideoBots import VideoBotsPage


class VideoBotsStatsPage(BasePage):
    title = "Copilot Analytics"  # "Create Interactive Video Bots"
    slug_versions = ["analytics", "stats"]
    workflow = (
        Workflow.VIDEO_BOTS
    )  # this is a hidden page, so this isn't used but type checking requires a workflow

    def _get_current_app_url(self):
        # this is overwritten to include the query params in the copied url for the share button
        args = dict(self.request.query_params)
        return furl(self.app_url(), args=args).tostr()

    def render(self):
        self._setup_render()

        if not self.request.user or self.request.user.is_anonymous:
            st.write("**Please Login to view stats for your bot integrations**")
            return
        if self.is_current_user_admin():
            bot_integrations = BotIntegration.objects.all().order_by(
                "platform", "-created_at"
            )
        else:
            bot_integrations = BotIntegration.objects.filter(
                billing_account_uid=self.request.user.uid
            ).order_by("platform", "-created_at")

        if bot_integrations.count() == 0:
            st.write(
                "**Please connect a bot to a platform to view stats for your bot integrations or login to an account with connected bot integrations**"
            )
            return

        allowed_bids = [bi.id for bi in bot_integrations]
        bid = self.request.query_params.get("bi_id", allowed_bids[0])
        if int(bid) not in allowed_bids:
            bid = allowed_bids[0]
        bi = BotIntegration.objects.get(id=bid)
        run_title = (
            bi.published_run.title
            if bi.published_run
            else bi.saved_run.page_title
            if bi.saved_run and bi.saved_run.page_title
            else "This Copilot Run"
            if bi.saved_run
            else "No Run Connected"
        )
        run_url = furl(bi.saved_run.get_app_url()).tostr() if bi.saved_run else ""

        with st.div(className="d-flex justify-content-between mt-4"):
            with st.div(className="d-lg-flex d-block align-items-center"):
                with st.tag("div", className="me-3 mb-1 mb-lg-0 py-2 py-lg-0"):
                    self._render_breadcrumbs(
                        [
                            (VideoBotsPage.title, VideoBotsPage.app_url()),
                            (run_title, run_url),
                            (
                                bi.name,
                                VideoBotsPage().get_tab_url(MenuTabs.integrations),
                            ),
                        ]
                    )

                author = (
                    AppUser.objects.filter(uid=bi.billing_account_uid).first()
                    or self.request.user
                )
                self.render_author(
                    author,
                    show_as_link=self.is_current_user_admin(),
                )

            with st.div(className="d-flex align-items-center"):
                with st.div(className="d-flex align-items-start right-action-icons"):
                    self._render_social_buttons(show_button_text=True)

        st.markdown(f"# 📊 {bi.name} Analytics")

        col1, col2 = st.columns([1, 2])

        with col1:
            conversations: ConversationQuerySet = Conversation.objects.filter(
                bot_integration__id=bid
            )  # type: ignore
            # due to things like personal convos for slack, each user can have multiple conversations
            users = set([convo.get_user_id() for convo in conversations])
            messages = Message.objects.filter(conversation__in=conversations)
            user_messages = messages.filter(role=CHATML_ROLE_USER)
            bot_messages = messages.filter(role=CHATML_ROLE_ASSISTANT)
            num_active_users_last_7_days = len(
                set(
                    [
                        message.conversation.get_user_id()
                        for message in user_messages.filter(
                            created_at__gte=datetime.now() - timedelta(days=7),
                        )
                    ]
                )
            )
            num_active_users_last_30_days = len(
                set(
                    [
                        message.conversation.get_user_id()
                        for message in user_messages.filter(
                            created_at__gte=datetime.now() - timedelta(days=30),
                        )
                    ]
                )
            )
            positive_feedbacks = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_UP,
            ).count()
            negative_feedbacks = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_DOWN,
            ).count()
            run_link = (
                f'Powered By: <a href="{run_url}" target="_blank">{run_title}</a>'
            )
            connection_detail = (
                bi.fb_page_name
                or bi.wa_phone_number
                or bi.ig_username
                or (bi.slack_team_name + " - " + bi.slack_channel_name)
            )
            st.markdown(
                f"""
                - Platform: {Platform(bi.platform).name.capitalize()}
                - Created on: {bi.created_at.strftime("%b %d, %Y")}
                - Last Updated: {bi.updated_at.strftime("%b %d, %Y")}
                - {run_link}
                - Connected to: {connection_detail}
                * {len(users)} Users
                * {num_active_users_last_7_days} Active Users (Last 7 Days)
                * {num_active_users_last_30_days} Active Users (Last 30 Days)
                * {conversations.count()} Conversations
                * {user_messages.count()} User Messages
                * {bot_messages.count()} Bot Messages
                * {messages.count()} Total Messages
                * {positive_feedbacks} Positive Feedbacks
                * {negative_feedbacks} Negative Feedbacks
                """,
                unsafe_allow_html=True,
            )
            start_of_year_date = datetime.now().replace(month=1, day=1)
            st.session_state.setdefault(
                "start_date",
                self.request.query_params.get(
                    "start_date", start_of_year_date.strftime("%Y-%m-%d")
                ),
            )
            start_date: datetime = st.date_input("Start date", key="start_date")  # type: ignore
            st.session_state.setdefault(
                "end_date",
                self.request.query_params.get(
                    "end_date", datetime.now().strftime("%Y-%m-%d")
                ),
            )
            end_date: datetime = st.date_input("End date", key="end_date")  # type: ignore
            st.session_state.setdefault(
                "view", self.request.query_params.get("view", "Weekly")
            )
            view = st.horizontal_radio(
                "### View",
                options=["Daily", "Weekly", "Monthly"],
                key="view",
                label_visibility="collapsed",
            )

        data = []
        date = start_date
        if view == "Weekly":
            delta = timedelta(days=7)
        elif view == "Daily":
            delta = timedelta(days=1)
        elif view == "Monthly":
            delta = relativedelta(months=1)
        else:
            delta = timedelta(days=1)
        while date <= end_date:
            messages_received = Message.objects.filter(
                created_at__date__gte=date,
                created_at__date__lt=date + delta,
            ).filter(conversation__bot_integration=bi, role=CHATML_ROLE_USER)

            unique_active_convos = (
                messages_received.values_list("conversation__id", flat=True)
                .distinct()
                .order_by()
            )

            unique_users = len(
                set(
                    [
                        convo.get_user_id()
                        for convo in Conversation.objects.filter(
                            id__in=unique_active_convos
                        )
                    ]
                )
            )

            unique_active_convos = unique_active_convos.count()

            positive_feedbacks = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_UP,
                created_at__date__gte=date,
                created_at__date__lt=date + delta,
            ).count()

            negative_feedbacks = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_DOWN,
                created_at__date__gte=date,
                created_at__date__lt=date + delta,
            ).count()

            unique_feedback_givers = (
                Conversation.objects.filter(
                    bot_integration=bi,
                    messages__feedbacks__isnull=False,
                    created_at__date__gte=date,
                    created_at__date__lt=date + delta,
                )
                .distinct()
                .count()
            )
            try:
                messages_per_unique_convo = round(
                    len(messages_received) / unique_active_convos
                )
            except ZeroDivisionError:
                messages_per_unique_convo = 0

            try:
                messages_per_unique_user = round(len(messages_received) / unique_users)
            except ZeroDivisionError:
                messages_per_unique_user = 0

            ctx = {
                "date": date,
                "Messages_Sent": len(messages_received),
                "Neg_feedback": negative_feedbacks,
                "Pos_feedback": positive_feedbacks,
                "Convos": unique_active_convos,
                "Senders": unique_users,
                "Unique_feedback_givers": unique_feedback_givers,
                "Msgs_per_convo": messages_per_unique_convo,
                "Msgs_per_user": messages_per_unique_user,
            }
            data.append(ctx)
            date += delta
        df = pd.DataFrame(data)

        with col2:
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=list(df["date"]),
                        y=list(df["Messages_Sent"]),
                        text=list(df["Messages_Sent"]),
                        texttemplate="<b>%{text}</b>",
                        insidetextanchor="middle",
                        insidetextfont=dict(size=24),
                        hovertemplate="Messages Sent: %{y:.0f}<extra></extra>",
                    ),
                ],
                layout=dict(
                    margin=dict(l=0, r=0, t=28, b=0),
                    yaxis=dict(title="User Messages Sent"),
                    xaxis=dict(title="Date"),
                    title=dict(
                        text=f"{view} Messages Sent",
                    ),
                    height=300,
                ),
            )
            st.plotly_chart(fig)
            fig = go.Figure(
                data=[
                    go.Scatter(
                        name="Senders",
                        mode="lines+markers",
                        x=list(df["date"]),
                        y=list(df["Senders"]),
                        text=list(df["Senders"]),
                        hovertemplate="Active Users: %{y:.0f}<extra></extra>",
                    ),
                    go.Scatter(
                        name="Conversations",
                        mode="lines+markers",
                        x=list(df["date"]),
                        y=list(df["Convos"]),
                        text=list(df["Convos"]),
                        hovertemplate="Conversations: %{y:.0f}<extra></extra>",
                    ),
                    go.Scatter(
                        name="Feedback Givers",
                        mode="lines+markers",
                        x=list(df["date"]),
                        y=list(df["Unique_feedback_givers"]),
                        text=list(df["Unique_feedback_givers"]),
                        hovertemplate="Feedback Givers: %{y:.0f}<extra></extra>",
                    ),
                    go.Scatter(
                        name="Positive Feedbacks",
                        mode="lines+markers",
                        x=list(df["date"]),
                        y=list(df["Pos_feedback"]),
                        text=list(df["Pos_feedback"]),
                        hovertemplate="Positive Feedbacks: %{y:.0f}<extra></extra>",
                    ),
                    go.Scatter(
                        name="Negative Feedbacks",
                        mode="lines+markers",
                        x=list(df["date"]),
                        y=list(df["Neg_feedback"]),
                        text=list(df["Neg_feedback"]),
                        hovertemplate="Negative Feedbacks: %{y:.0f}<extra></extra>",
                    ),
                    go.Scatter(
                        name="Messages per Convo",
                        mode="lines+markers",
                        x=list(df["date"]),
                        y=list(df["Msgs_per_convo"]),
                        text=list(df["Msgs_per_convo"]),
                        hovertemplate="Messages per Convo: %{y:.0f}<extra></extra>",
                    ),
                    go.Scatter(
                        name="Messages per Sender",
                        mode="lines+markers",
                        x=list(df["date"]),
                        y=list(df["Msgs_per_user"]),
                        text=list(df["Msgs_per_user"]),
                        hovertemplate="Messages per User: %{y:.0f}<extra></extra>",
                    ),
                ],
                layout=dict(
                    margin=dict(l=0, r=0, t=28, b=0),
                    yaxis=dict(title="Unique Count"),
                    xaxis=dict(title="Date"),
                    title=dict(
                        text=f"{view} Usage Trends",
                    ),
                    height=300,
                ),
            )
            st.plotly_chart(fig)

        st.write("---")
        st.session_state.setdefault("details", self.request.query_params.get("details"))
        details = st.horizontal_radio(
            "### Details",
            options=[
                "All Conversations",
                "Feedback Positive",
                "Feedback Negative",
                "Answered Successfully",
                "Answered Unsuccessfully",
            ],
            key="details",
        )

        if details == "All Conversations":
            df = conversations.to_df()
        elif details == "Feedback Positive":
            pos_feedbacks: FeedbackQuerySet = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_UP,
            )  # type: ignore
            df = pos_feedbacks.to_df()
        elif details == "Feedback Negative":
            neg_feedbacks: FeedbackQuerySet = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_DOWN,
            )  # type: ignore
            df = neg_feedbacks.to_df()
        elif details == "Answered Successfully":
            successful_messages: MessageQuerySet = Message.objects.filter(
                conversation__bot_integration=bi,
                analysis_result__contains={"Answered": True},
            )  # type: ignore
            df = successful_messages.to_df()
        elif details == "Answered Unsuccessfully":
            unsuccessful_messages: MessageQuerySet = Message.objects.filter(
                conversation__bot_integration=bi,
                analysis_result__contains={"Answered": False},
            )  # type: ignore
            df = unsuccessful_messages.to_df()

        if not df.empty:
            columns = df.columns.tolist()
            st.data_table(
                [[col.capitalize() for col in columns]]
                + [
                    [
                        dict(
                            readonly=True,
                            displayData=str(df.iloc[idx, col]),
                            data=str(df.iloc[idx, col]),
                        )
                        for col in range(len(columns))
                    ]
                    for idx in range(len(df))
                ]
            )
            # download as csv button
            csv = df.to_csv()
            b64 = base64.b64encode(csv.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="{bi.name}.csv">Download CSV File</a>'
            st.markdown(href, unsafe_allow_html=True)
        else:
            st.write("No data to show yet.")

        # we store important inputs in the url so the user can return to the same view (e.g. bookmark it)
        # this also allows them to share the url (once organizations are supported)
        # and allows us to share a url to a specific view with users
        new_url = furl(
            self.app_url(),
            args={
                "bi_id": bid,
                "view": view,
                "details": details,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
            },
        ).tostr()
        st.change_url(new_url, self.request)
