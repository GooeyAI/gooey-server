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
import pandas as pd
import plotly.graph_objects as go
import base64
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
)
from recipes.VideoBots import VideoBotsPage
from django.db.models.functions import (
    TruncMonth,
    TruncDay,
    TruncWeek,
    TruncYear,
    Concat,
)
from django.db.models import Count

ID_COLUMNS = [
    "conversation__fb_page_id",
    "conversation__ig_account_id",
    "conversation__wa_phone_number",
    "conversation__slack_user_id",
]


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

    def show_title_breadcrumb_share(self, run_title, run_url, bi):
        with st.div(className="d-flex justify-content-between mt-4"):
            with st.div(className="d-lg-flex d-block align-items-center"):
                with st.tag("div", className="me-3 mb-1 mb-lg-0 py-2 py-lg-0"):
                    with st.breadcrumbs():
                        st.breadcrumb_item(
                            VideoBotsPage.title,
                            link_to=VideoBotsPage.app_url(),
                            className="text-muted",
                        )
                        st.breadcrumb_item(
                            run_title,
                            link_to=run_url,
                            className="text-muted",
                        )
                        st.breadcrumb_item(
                            "Integrations",
                            link_to=VideoBotsPage().get_tab_url(MenuTabs.integrations),
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

    def render(self):
        self.setup_render()

        if not self.request.user or self.request.user.is_anonymous:
            st.write("**Please Login to view stats for your bot integrations**")
            return
        if not self.request.user.is_paying and not self.is_current_user_admin():
            st.write(
                "**Please upgrade to a paid plan to view stats for your bot integrations**"
            )
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
        run_title, run_url = self.parse_run_info(bi)

        self.show_title_breadcrumb_share(run_title, run_url, bi)

        col1, col2 = st.columns([1, 2])

        with col1:
            conversations, messages = self.calculate_overall_stats(
                bid, bi, run_title, run_url
            )

            (
                start_date,
                end_date,
                view,
                factor,
                trunc_fn,
            ) = self.render_date_view_inputs()

        df = self.calculate_stats_binned_by_time(
            bi, start_date, end_date, factor, trunc_fn
        )

        if df.empty or "date" not in df.columns:
            st.write("No data to show yet.")
            return

        with col2:
            self.plot_graphs(view, df)

        st.write("---")
        st.session_state.setdefault("details", self.request.query_params.get("details"))
        details = st.horizontal_radio(
            "### Details",
            options=[
                "Conversations",
                "Messages",
                "Feedback Positive",
                "Feedback Negative",
                "Answered Successfully",
                "Answered Unsuccessfully",
            ],
            key="details",
        )

        if details == "Conversations":
            options = [
                "Messages",
                "Correct Answers",
                "Thumbs up",
                "Name",
            ]
        elif details == "Feedback Positive":
            options = [
                "Name",
                "Rating",
                "Question Answered",
            ]
        elif details == "Feedback Negative":
            options = [
                "Name",
                "Rating",
                "Question Answered",
            ]
        elif details == "Answered Successfully":
            options = [
                "Name",
                "Sent",
            ]
        elif details == "Answered Unsuccessfully":
            options = [
                "Name",
                "Sent",
            ]
        else:
            options = []

        sort_by = None
        if options:
            query_sort_by = self.request.query_params.get("sort_by")
            st.session_state.setdefault(
                "sort_by", query_sort_by if query_sort_by in options else options[0]
            )
            st.selectbox(
                "Sort by",
                options=options,
                key="sort_by",
            )
            sort_by = st.session_state["sort_by"]

        df = self.get_tabular_data(
            bi, run_url, conversations, messages, details, sort_by, rows=500
        )

        if not df.empty:
            columns = df.columns.tolist()
            st.data_table(
                [columns]
                + [
                    [
                        dict(
                            readonly=True,
                            displayData=str(df.iloc[idx, col]),
                            data=str(df.iloc[idx, col]),
                        )
                        for col in range(len(columns))
                    ]
                    for idx in range(min(500, len(df)))
                ]
            )
            # download as csv button
            st.html("<br/>")
            if st.checkbox("Export"):
                df = self.get_tabular_data(
                    bi, run_url, conversations, messages, details, sort_by
                )
                csv = df.to_csv()
                b64 = base64.b64encode(csv.encode()).decode()
                st.html(
                    f'<a href="data:file/csv;base64,{b64}" download="{bi.name}.csv" class="btn btn-theme btn-secondary">Download CSV File</a>'
                )
                st.caption("Includes full data (UI only shows first 500 rows)")
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
                "sort_by": sort_by,
            },
        ).tostr()
        st.change_url(new_url, self.request)

    def render_date_view_inputs(self):
        start_of_year_date = datetime.now().replace(month=1, day=1)
        st.session_state.setdefault(
            "start_date",
            self.request.query_params.get(
                "start_date", start_of_year_date.strftime("%Y-%m-%d")
            ),
        )
        start_date: datetime = (
            st.date_input("Start date", key="start_date") or start_of_year_date
        )
        st.session_state.setdefault(
            "end_date",
            self.request.query_params.get(
                "end_date", datetime.now().strftime("%Y-%m-%d")
            ),
        )
        end_date: datetime = st.date_input("End date", key="end_date") or datetime.now()
        st.session_state.setdefault(
            "view", self.request.query_params.get("view", "Weekly")
        )
        view = st.horizontal_radio(
            "### View",
            options=["Daily", "Weekly", "Monthly"],
            key="view",
            label_visibility="collapsed",
        )
        factor = 1
        if view == "Weekly":
            trunc_fn = TruncWeek
        elif view == "Daily":
            if end_date - start_date > timedelta(days=31):
                st.write(
                    "**Note: Date ranges greater than 31 days show weekly averages in daily view**"
                )
                factor = 1.0 / 7.0
                trunc_fn = TruncWeek
            else:
                trunc_fn = TruncDay
        elif view == "Monthly":
            trunc_fn = TruncMonth
        else:
            trunc_fn = TruncYear
        return start_date, end_date, view, factor, trunc_fn

    def parse_run_info(self, bi):
        saved_run = bi.get_active_saved_run()
        run_title = (
            bi.published_run.title
            if bi.published_run
            else (
                saved_run.page_title
                if saved_run and saved_run.page_title
                else "This Copilot Run" if saved_run else "No Run Connected"
            )
        )
        run_url = furl(saved_run.get_app_url()).tostr() if saved_run else ""
        return run_title, run_url

    def calculate_overall_stats(self, bid, bi, run_title, run_url):
        conversations: ConversationQuerySet = Conversation.objects.filter(
            bot_integration__id=bid
        ).order_by()  # type: ignore
        # due to things like personal convos for slack, each user can have multiple conversations
        users = conversations.get_unique_users().order_by()
        messages: MessageQuerySet = Message.objects.filter(conversation__in=conversations).order_by()  # type: ignore
        user_messages = messages.filter(role=CHATML_ROLE_USER).order_by()
        bot_messages = messages.filter(role=CHATML_ROLE_ASSISTANT).order_by()
        num_active_users_last_7_days = (
            user_messages.filter(
                conversation__in=users,
                created_at__gte=datetime.now() - timedelta(days=7),
            )
            .distinct(
                *ID_COLUMNS,
            )
            .count()
        )
        num_active_users_last_30_days = (
            user_messages.filter(
                conversation__in=users,
                created_at__gte=datetime.now() - timedelta(days=30),
            )
            .distinct(
                *ID_COLUMNS,
            )
            .count()
        )
        positive_feedbacks = Feedback.objects.filter(
            message__conversation__bot_integration=bi,
            rating=Feedback.Rating.RATING_THUMBS_UP,
        ).count()
        negative_feedbacks = Feedback.objects.filter(
            message__conversation__bot_integration=bi,
            rating=Feedback.Rating.RATING_THUMBS_DOWN,
        ).count()
        run_link = f'Powered By: <a href="{run_url}" target="_blank">{run_title}</a>'
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
                * {users.count()} Users
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

        return conversations, messages

    def calculate_stats_binned_by_time(
        self, bi, start_date, end_date, factor, trunc_fn
    ):
        messages_received = (
            Message.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                conversation__bot_integration=bi,
                role=CHATML_ROLE_USER,
            )
            .order_by()
            .annotate(date=trunc_fn("created_at"))
            .values("date")
            .annotate(Messages_Sent=Count("id"))
            .annotate(Convos=Count("conversation_id", distinct=True))
            .annotate(
                Senders=Count(
                    Concat(
                        *ID_COLUMNS,
                    ),
                    distinct=True,
                )
            )
            .annotate(Unique_feedback_givers=Count("feedbacks", distinct=True))
            .values(
                "date",
                "Messages_Sent",
                "Convos",
                "Senders",
                "Unique_feedback_givers",
            )
        )

        positive_feedbacks = (
            Feedback.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_UP,
            )
            .order_by()
            .annotate(date=trunc_fn("created_at"))
            .values("date")
            .annotate(Pos_feedback=Count("id"))
            .values("date", "Pos_feedback")
        )

        negative_feedbacks = (
            Feedback.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_DOWN,
            )
            .order_by()
            .annotate(date=trunc_fn("created_at"))
            .values("date")
            .annotate(Neg_feedback=Count("id"))
            .values("date", "Neg_feedback")
        )

        df = pd.DataFrame(
            messages_received,
            columns=[
                "date",
                "Messages_Sent",
                "Convos",
                "Senders",
                "Unique_feedback_givers",
            ],
        )
        df = df.merge(
            pd.DataFrame(positive_feedbacks, columns=["date", "Pos_feedback"]),
            how="outer",
            left_on="date",
            right_on="date",
        )
        df = df.merge(
            pd.DataFrame(negative_feedbacks, columns=["date", "Neg_feedback"]),
            how="outer",
            left_on="date",
            right_on="date",
        )
        df["Messages_Sent"] = df["Messages_Sent"] * factor
        df["Convos"] = df["Convos"] * factor
        df["Senders"] = df["Senders"] * factor
        df["Unique_feedback_givers"] = df["Unique_feedback_givers"] * factor
        df["Pos_feedback"] = df["Pos_feedback"] * factor
        df["Neg_feedback"] = df["Neg_feedback"] * factor
        df["Msgs_per_convo"] = df["Messages_Sent"] / df["Convos"]
        df["Msgs_per_user"] = df["Messages_Sent"] / df["Senders"]
        df.fillna(0, inplace=True)
        df = df.round(0).astype("int32", errors="ignore")
        return df

    def plot_graphs(self, view, df):
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
                yaxis=dict(
                    title="User Messages Sent",
                    range=[
                        0,
                        df["Messages_Sent"].max() + 10,
                    ],
                    tickvals=[
                        *range(
                            int(df["Messages_Sent"].max() / 10),
                            int(df["Messages_Sent"].max()) + 1,
                            int(df["Messages_Sent"].max() / 10) + 1,
                        )
                    ],
                ),
                title=dict(
                    text=f"{view} Messages Sent",
                ),
                height=300,
                template="plotly_white",
            ),
        )
        st.plotly_chart(fig)
        st.write("---")
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
                yaxis=dict(
                    title="Unique Count",
                ),
                title=dict(
                    text=f"{view} Usage Trends",
                ),
                height=300,
                template="plotly_white",
            ),
        )
        max_value = (
            df[
                [
                    "Senders",
                    "Convos",
                    "Unique_feedback_givers",
                    "Pos_feedback",
                    "Neg_feedback",
                    "Msgs_per_convo",
                    "Msgs_per_user",
                ]
            ]
            .max()
            .max()
        )
        if max_value < 10:
            # only set fixed axis scale if the data doesn't have enough values to make it look good
            # otherwise default behaviour is better since it adapts when user deselects a line
            fig.update_yaxes(
                range=[
                    -0.2,
                    max_value + 10,
                ],
                tickvals=[
                    *range(
                        int(max_value / 10),
                        int(max_value) + 10,
                        int(max_value / 10) + 1,
                    )
                ],
            )
        st.plotly_chart(fig)

    def get_tabular_data(
        self, bi, run_url, conversations, messages, details, sort_by, rows=10000
    ):
        df = pd.DataFrame()
        if details == "Conversations":
            df = conversations.to_df_format(row_limit=rows)
        elif details == "Messages":
            df = messages.order_by("-created_at", "conversation__id").to_df_format(
                row_limit=rows
            )
            df = df.sort_values(by=["Name", "Sent"], ascending=False).reset_index()
            df.drop(columns=["index"], inplace=True)
        elif details == "Feedback Positive":
            pos_feedbacks: FeedbackQuerySet = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_UP,
            )  # type: ignore
            df = pos_feedbacks.to_df_format(row_limit=rows)
            df["Run URL"] = run_url
            df["Bot"] = bi.name
        elif details == "Feedback Negative":
            neg_feedbacks: FeedbackQuerySet = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_DOWN,
            )  # type: ignore
            df = neg_feedbacks.to_df_format(row_limit=rows)
            df["Run URL"] = run_url
            df["Bot"] = bi.name
        elif details == "Answered Successfully":
            successful_messages: MessageQuerySet = Message.objects.filter(
                conversation__bot_integration=bi,
                analysis_result__contains={"Answered": True},
            )  # type: ignore
            df = successful_messages.to_df_analysis_format(row_limit=rows)
            df["Run URL"] = run_url
            df["Bot"] = bi.name
        elif details == "Answered Unsuccessfully":
            unsuccessful_messages: MessageQuerySet = Message.objects.filter(
                conversation__bot_integration=bi,
                analysis_result__contains={"Answered": False},
            )  # type: ignore
            df = unsuccessful_messages.to_df_analysis_format(row_limit=rows)
            df["Run URL"] = run_url
            df["Bot"] = bi.name

        if sort_by and sort_by in df.columns:
            df.sort_values(by=[sort_by], ascending=False, inplace=True)

        return df
