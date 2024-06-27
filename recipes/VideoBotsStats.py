import base64
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Avg, Q
from django.db.models.functions import (
    TruncMonth,
    TruncDay,
    TruncWeek,
    TruncYear,
    Concat,
)
from django.utils import timezone
from fastapi import HTTPException
from furl import furl
from pydantic import BaseModel

import gooey_ui as st
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
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage, RecipeTabs
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
)
from gooey_ui import RedirectException
from recipes.VideoBots import VideoBotsPage

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

    class RequestModel(BaseModel):
        pass

    class ResponseModel(BaseModel):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bi = None

    def current_app_url(
        self,
        tab: RecipeTabs = RecipeTabs.run,
        query_params: dict = None,
        path_params: dict = None,
    ) -> str:
        return str(furl(settings.APP_BASE_URL) / self.request.url.path)

    def show_title_breadcrumb_share(
        self, bi: BotIntegration, run_title: str, run_url: str
    ):
        with st.div(className="d-flex justify-content-between mt-4"):
            with st.div(className="d-lg-flex d-block align-items-center"):
                with st.tag("div", className="me-3 mb-1 mb-lg-0 py-2 py-lg-0"):
                    with st.breadcrumbs():
                        metadata = VideoBotsPage.workflow.get_or_create_metadata()
                        st.breadcrumb_item(
                            metadata.short_title,
                            link_to=VideoBotsPage.app_url(),
                            className="text-muted",
                        )
                        if not (bi.published_run_id and bi.published_run.is_root()):
                            st.breadcrumb_item(
                                run_title,
                                link_to=run_url,
                                className="text-muted",
                            )
                        st.breadcrumb_item(
                            "Integrations",
                            link_to=VideoBotsPage.current_app_url(
                                RecipeTabs.integrations,
                                path_params=dict(
                                    integration_id=bi.api_integration_id()
                                ),
                            ),
                        )

                author = (
                    AppUser.objects.filter(uid=bi.billing_account_uid).first()
                    or self.request.user
                )
                VideoBotsPage.render_author(
                    author,
                    show_as_link=self.is_current_user_admin(),
                )

            with st.div(className="d-flex align-items-center"):
                with st.div(className="d-flex align-items-start right-action-icons"):
                    self._render_social_buttons(show_button_text=True)

        st.markdown("# " + self.get_dynamic_meta_title())

    def get_dynamic_meta_title(self):
        return f"📊 {self.bi.name} Analytics" if self.bi else self.title

    def render(self):
        self.setup_sentry()

        if not self.request.user or self.request.user.is_anonymous:
            st.write("**Please Login to view stats for your bot integrations**")
            return
        if not self.request.user.is_paying and not self.is_current_user_admin():
            st.write(
                "**Please upgrade to a paid plan to view stats for your bot integrations**"
            )
            return
        if self.is_current_user_admin():
            bi_qs = BotIntegration.objects.all().order_by("platform", "-created_at")
        else:
            bi_qs = BotIntegration.objects.filter(
                billing_account_uid=self.request.user.uid
            ).order_by("platform", "-created_at")

        if not bi_qs.exists():
            st.write(
                "**Please connect a bot to a platform to view stats for your bot integrations or login to an account with connected bot integrations**"
            )
            return

        bi_id = self.request.query_params.get("bi_id") or st.session_state.get("bi_id")
        try:
            self.bi = bi = bi_qs.get(id=bi_id)
        except BotIntegration.DoesNotExist:
            raise HTTPException(status_code=404, detail="Bot Integration not found")

        # for backwards compatibility with old urls
        if self.request.query_params.get("bi_id"):
            raise RedirectException(
                str(
                    furl(
                        VideoBotsPage.app_url(
                            tab=RecipeTabs.integrations,
                            example_id=(
                                bi.published_run and bi.published_run.published_run_id
                            ),
                            path_params=dict(integration_id=bi.api_integration_id()),
                        )
                    )
                    / "stats/"
                )
            )

        run_url = VideoBotsPage.current_app_url()
        if bi.published_run_id:
            run_title = bi.published_run.title
        else:
            run_title = bi.saved_run.page_title  # this is mostly for backwards compat
        self.show_title_breadcrumb_share(bi, run_title, run_url)

        col1, col2 = st.columns([1, 2])

        with col1:
            conversations, messages = self.calculate_overall_stats(
                bi, run_title, run_url
            )

            (
                start_date,
                end_date,
                view,
                factor,
                trunc_fn,
            ) = self.render_date_view_inputs(bi)

        df = self.calculate_stats_binned_by_time(
            bi, start_date, end_date, factor, trunc_fn
        )

        if df.empty or "date" not in df.columns:
            st.write("No data to show yet.")
            self.update_url(
                view,
                st.session_state.get("details"),
                start_date,
                end_date,
                st.session_state.get("sort_by"),
            )
            return

        with col2:
            self.plot_graphs(view, df)

        st.write("---")
        st.session_state.setdefault("details", self.request.query_params.get("details"))
        details = st.horizontal_radio(
            "### Details",
            options=(
                [
                    "Conversations",
                    "Messages",
                    "Feedback Positive",
                    "Feedback Negative",
                ]
                + (
                    [
                        "Answered Successfully",
                        "Answered Unsuccessfully",
                    ]
                    if bi.analysis_runs.exists()
                    else []
                )
            ),
            key="details",
        )

        if details == "Conversations":
            options = [
                "Last Sent",
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
            bi,
            conversations,
            messages,
            details,
            sort_by,
            rows=500,
            start_date=start_date,
            end_date=end_date,
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
                    bi,
                    conversations,
                    messages,
                    details,
                    sort_by,
                    start_date=start_date,
                    end_date=end_date,
                )
                csv = df.to_csv()
                b64 = base64.b64encode(csv.encode()).decode()
                st.html(
                    f'<a href="data:file/csv;base64,{b64}" download="{bi.name}.csv" class="btn btn-theme btn-secondary">Download CSV File</a>'
                )
                st.caption("Includes full data (UI only shows first 500 rows)")
        else:
            st.write("No data to show yet.")

        self.update_url(view, details, start_date, end_date, sort_by)

    # we store important inputs in the url so the user can return to the same view (e.g. bookmark it)
    # this also allows them to share the url (once organizations are supported)
    # and allows us to share a url to a specific view with users
    def update_url(self, view, details, start_date, end_date, sort_by):
        f = furl(str(self.request.url))
        new_query_params = {
            "view": view or "",
            "details": details or "",
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "sort_by": sort_by or "",
        }
        if f.query.params == new_query_params:
            return
        raise RedirectException(str(f.set(query_params=new_query_params)))

    def render_date_view_inputs(self, bi):
        if st.checkbox("Show All"):
            start_date = bi.created_at
            end_date = timezone.now() + timedelta(days=1)
        else:
            fifteen_days_ago = timezone.now() - timedelta(days=15)
            fifteen_days_ago = fifteen_days_ago.replace(hour=0, minute=0, second=0)
            st.session_state.setdefault(
                "start_date",
                self.request.query_params.get(
                    "start_date", fifteen_days_ago.strftime("%Y-%m-%d")
                ),
            )
            start_date: datetime = (
                st.date_input("Start date", key="start_date") or fifteen_days_ago
            )
            st.session_state.setdefault(
                "end_date",
                self.request.query_params.get(
                    "end_date",
                    (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                ),
            )
            end_date: datetime = (
                st.date_input("End date", key="end_date") or timezone.now()
            )
            st.session_state.setdefault(
                "view", self.request.query_params.get("view", "Daily")
            )
        st.write("---")
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
            start_date = start_date.replace(day=1)
            st.session_state["start_date"] = start_date.strftime("%Y-%m-%d")
            if end_date.day != 1:
                end_date = end_date.replace(day=1) + relativedelta(months=1)
                st.session_state["end_date"] = end_date.strftime("%Y-%m-%d")
        else:
            trunc_fn = TruncYear
        return start_date, end_date, view, factor, trunc_fn

    def calculate_overall_stats(self, bi, run_title, run_url):
        conversations: ConversationQuerySet = Conversation.objects.filter(
            bot_integration=bi
        ).order_by()  # type: ignore
        # due to things like personal convos for slack, each user can have multiple conversations
        users = conversations.get_unique_users().order_by()
        messages: MessageQuerySet = Message.objects.filter(conversation__in=conversations).order_by()  # type: ignore
        user_messages = messages.filter(role=CHATML_ROLE_USER).order_by()
        bot_messages = messages.filter(role=CHATML_ROLE_ASSISTANT).order_by()
        num_active_users_last_7_days = (
            user_messages.filter(
                conversation__in=users,
                created_at__gte=timezone.now() - timedelta(days=7),
            )
            .distinct(
                *ID_COLUMNS,
            )
            .count()
        )
        num_active_users_last_30_days = (
            user_messages.filter(
                conversation__in=users,
                created_at__gte=timezone.now() - timedelta(days=30),
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
        connection_detail = bi.get_display_name()
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
        import pandas as pd

        messages_received = (
            Message.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                conversation__bot_integration=bi,
                role=CHATML_ROLE_ASSISTANT,
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
            .annotate(Average_runtime=Avg("saved_run__run_time"))
            .annotate(Unique_feedback_givers=Count("feedbacks", distinct=True))
            .values(
                "date",
                "Messages_Sent",
                "Convos",
                "Senders",
                "Unique_feedback_givers",
                "Average_runtime",
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

        successfully_answered = (
            Message.objects.filter(
                conversation__bot_integration=bi,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            )
            .filter(
                Q(analysis_result__contains={"Answered": True})
                | Q(analysis_result__contains={"assistant": {"answer": "Found"}}),
            )
            .order_by()
            .annotate(date=trunc_fn("created_at"))
            .values("date")
            .annotate(Successfully_Answered=Count("id"))
            .values("date", "Successfully_Answered")
        )

        df = pd.DataFrame(
            messages_received,
            columns=[
                "date",
                "Messages_Sent",
                "Convos",
                "Senders",
                "Unique_feedback_givers",
                "Average_runtime",
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
        df = df.merge(
            pd.DataFrame(
                successfully_answered, columns=["date", "Successfully_Answered"]
            ),
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
        df["Percentage_positive_feedback"] = (
            df["Pos_feedback"] / df["Messages_Sent"]
        ) * 100
        df["Percentage_negative_feedback"] = (
            df["Neg_feedback"] / df["Messages_Sent"]
        ) * 100
        df["Percentage_successfully_answered"] = (
            df["Successfully_Answered"] / df["Messages_Sent"]
        ) * 100
        df["Msgs_per_convo"] = df["Messages_Sent"] / df["Convos"]
        df["Msgs_per_user"] = df["Messages_Sent"] / df["Senders"]
        df.fillna(0, inplace=True)
        df = df.round(0).astype("int32", errors="ignore")
        df = df.sort_values(by=["date"], ascending=True).reset_index()
        return df

    def plot_graphs(self, view, df):
        import plotly.graph_objects as go

        dateformat = "%B %Y" if view == "Monthly" else "%x"
        xaxis_ticks = dict(
            tickmode="array",
            tickvals=list(df["date"]),
            ticktext=list(df["date"].apply(lambda x: x.strftime(dateformat))),
        )

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
                        df["Messages_Sent"].max() + 1,
                    ],
                    tickvals=[
                        *range(
                            int(df["Messages_Sent"].max() / 10),
                            int(df["Messages_Sent"].max()) + 1,
                            int(df["Messages_Sent"].max() / 10) + 1,
                        )
                    ],
                ),
                xaxis=xaxis_ticks,
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
                xaxis=xaxis_ticks,
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
        st.write("---")
        fig = go.Figure(
            data=[
                go.Scatter(
                    name="Average Run Time",
                    mode="lines+markers",
                    x=list(df["date"]),
                    y=list(df["Average_runtime"]),
                    text=list(df["Average_runtime"]),
                    hovertemplate="Average Runtime: %{y:.0f}<extra></extra>",
                ),
            ],
            layout=dict(
                margin=dict(l=0, r=0, t=28, b=0),
                yaxis=dict(
                    title="Seconds",
                ),
                title=dict(
                    text=f"{view} Performance Metrics",
                ),
                xaxis=xaxis_ticks,
                height=300,
                template="plotly_white",
            ),
        )
        st.plotly_chart(fig)
        st.write("---")
        fig = go.Figure(
            data=[
                go.Scatter(
                    name="Positive Feedback",
                    mode="lines+markers",
                    x=list(df["date"]),
                    y=list(df["Percentage_positive_feedback"]),
                    text=list(df["Percentage_positive_feedback"]),
                    hovertemplate="Positive Feedback: %{y:.0f}%<extra></extra>",
                ),
                go.Scatter(
                    name="Negative Feedback",
                    mode="lines+markers",
                    x=list(df["date"]),
                    y=list(df["Percentage_negative_feedback"]),
                    text=list(df["Percentage_negative_feedback"]),
                    hovertemplate="Negative Feedback: %{y:.0f}%<extra></extra>",
                ),
                go.Scatter(
                    name="Successfully Answered",
                    mode="lines+markers",
                    x=list(df["date"]),
                    y=list(df["Percentage_successfully_answered"]),
                    text=list(df["Percentage_successfully_answered"]),
                    hovertemplate="Successfully Answered: %{y:.0f}%<extra></extra>",
                ),
            ],
            layout=dict(
                margin=dict(l=0, r=0, t=28, b=0),
                yaxis=dict(
                    title="Percentage",
                    range=[0, 100],
                    tickvals=[
                        *range(
                            0,
                            101,
                            10,
                        )
                    ],
                ),
                xaxis=xaxis_ticks,
                title=dict(
                    text=f"{view} Feedback Distribution",
                ),
                height=300,
                template="plotly_white",
            ),
        )
        st.plotly_chart(fig)

    def get_tabular_data(
        self,
        bi,
        conversations,
        messages,
        details,
        sort_by,
        rows=10000,
        start_date=None,
        end_date=None,
    ):
        import pandas as pd

        df = pd.DataFrame()
        if details == "Conversations":
            if start_date and end_date:
                messages = messages.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )
                conversations = conversations.filter(messages__in=messages).distinct()
            df = conversations.to_df_format(row_limit=rows)
        elif details == "Messages":
            if start_date and end_date:
                messages = messages.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )
            df = messages.order_by("-created_at", "conversation__id").to_df_format(
                row_limit=rows
            )
            most_recent = (
                df.groupby("Name")["Sent"]
                .max()
                .reset_index()
                .rename(columns={"Sent": "Last Sent"})
            )
            df = df.merge(
                most_recent,
                how="left",
                left_on="Name",
                right_on="Name",
            )
            df = df.sort_values(
                by=["Last Sent", "Name", "Sent"], ascending=False
            ).reset_index()
            df.drop(columns=["index", "Last Sent"], inplace=True)
        elif details == "Feedback Positive":
            pos_feedbacks: FeedbackQuerySet = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_UP,
            )  # type: ignore
            if start_date and end_date:
                pos_feedbacks = pos_feedbacks.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )
            df = pos_feedbacks.to_df_format(row_limit=rows)
        elif details == "Feedback Negative":
            neg_feedbacks: FeedbackQuerySet = Feedback.objects.filter(
                message__conversation__bot_integration=bi,
                rating=Feedback.Rating.RATING_THUMBS_DOWN,
            )  # type: ignore
            if start_date and end_date:
                neg_feedbacks = neg_feedbacks.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )
            df = neg_feedbacks.to_df_format(row_limit=rows)
        elif details == "Answered Successfully":
            successful_messages: MessageQuerySet = Message.objects.filter(
                Q(analysis_result__contains={"Answered": True})
                | Q(analysis_result__contains={"assistant": {"answer": "Found"}}),
                conversation__bot_integration=bi,
            )  # type: ignore
            if start_date and end_date:
                successful_messages = successful_messages.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )
            df = successful_messages.to_df_analysis_format(row_limit=rows)
        elif details == "Answered Unsuccessfully":
            unsuccessful_messages: MessageQuerySet = Message.objects.filter(
                Q(analysis_result__contains={"Answered": False})
                | Q(analysis_result__contains={"assistant": {"answer": "Missing"}}),
                conversation__bot_integration=bi,
            )  # type: ignore
            if start_date and end_date:
                unsuccessful_messages = unsuccessful_messages.filter(
                    created_at__date__gte=start_date, created_at__date__lte=end_date
                )
            df = unsuccessful_messages.to_df_analysis_format(row_limit=rows)

        if sort_by and sort_by in df.columns:
            df.sort_values(by=[sort_by], ascending=False, inplace=True)

        return df
