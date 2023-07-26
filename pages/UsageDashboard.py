import plotly.graph_objects as go
from django.db.models import Q, QuerySet, Count, Func

from bots.models import SavedRun, Workflow
from gooeysite import wsgi

assert wsgi

from app_users.models import AppUser
import datetime
from multiprocessing.pool import ThreadPool
import pandas as pd
import plotly.express as px
import pytz
import streamlit as st

st.set_page_config(layout="wide")

team_emails = [
    "devxpy@gmail.com",
    "devxpy.spam@gmail.com",
    "sean@blagsvedt.com",
    "ambika@ajaibghar.com",
    "faraazmohd07@gmail.com",
]
team_user_Q = (
    Q(email__in=team_emails)
    | Q(email__endswith="gooey.ai")
    | Q(email__endswith="dara.network")
    | Q(email__endswith="gooey.ai")
    | Q(email__endswith="jaaga.in")
)


def main():
    st.write(
        """
### User Selection
# """
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        last_n_days = st.number_input("Last n Days", min_value=1, value=14)
    with col2:
        datepart = st.selectbox("Frequency", options=["day", "week", "hour", "month"])
    with col3:
        timezone = st.text_input("Timezone", value="Asia/Kolkata")

    col1, col2, col3 = st.columns(3)
    with col1:
        exclude_anon = st.checkbox("Exclude Anonymous", value=True)
    with col2:
        exclude_team = st.checkbox("Exclude Team", value=True)
    with col3:
        exclude_disabled = st.checkbox("Exclude Banned", value=True)

    now = datetime.datetime.now(pytz.timezone(timezone))
    today = datetime.datetime.date(now)
    time_offset = today - pd.offsets.Day(last_n_days - 1)

    app_users = get_filtered_app_users(
        exclude_anon=exclude_anon,
        exclude_disabled=exclude_disabled,
        exclude_team=exclude_team,
    )

    signups = app_users.filter(created_at__gte=time_offset).order_by("-created_at")
    st.write(f"### {signups.count()} Sign-ups")
    user_signups_df = pd.DataFrame.from_records(
        [
            {
                "uid": user.uid,
                "display_name": user.display_name,
                "email": str(user.email or user.phone_number),
                "created_at": user.created_at.astimezone(pytz.timezone(timezone)),
                "balance": user.balance,
            }
            for user in signups
        ]
    )
    if st.checkbox("Show All Sign-ups"):
        st.dataframe(user_signups_df)
    else:
        st.dataframe(user_signups_df.head(100))

    saved_runs_qs = SavedRun.objects.filter(
        created_at__gt=time_offset,
        run_id__isnull=False,
        uid__isnull=False,
        uid__in=app_users.values("uid"),
    )

    sorted_workflows = list(Workflow)
    workflow_counts = (
        saved_runs_qs.values("workflow")
        .annotate(count=Count("run_id"))
        .values("workflow", "count")
    )
    sorted_workflows.sort(
        key=lambda x: -next(
            (sr["count"] for sr in workflow_counts if sr["workflow"] == x), 0
        ),
    )

    counts_df = pd.DataFrame.from_records(
        (
            saved_runs_qs.values("uid")
            .annotate(
                all_recipes=Count("run_id"),
                **{
                    workflow.label: Count("run_id", filter=Q(workflow=workflow))
                    for workflow in sorted_workflows
                },
                total_errors=Count("error_msg", filter=~Q(error_msg="")),
                stuck_running=Count("run_id", filter=Q(run_status="Running...")),
                stuck_starting=Count("run_id", filter=Q(run_status="Starting...")),
            )
            .filter(all_recipes__gt=0)
        )
    )
    counts_df = merge_user_data(counts_df, counts_df["uid"])
    counts_df = counts_df.sort_values("all_recipes", ascending=False)
    st.write(
        f"""
### {len(counts_df)} Active Users
Pro Tip: Click on the table, then Press Ctrl/Cmd + F to search. 
Press Ctrl/Cmd + A to copy all and paste into a excel.
        """
    )
    if st.checkbox("Show All Users"):
        st.dataframe(counts_df)
    else:
        st.dataframe(counts_df.head(100))

    st.write("### Show User Runs")
    users = st.text_area("Enter User IDs (on separate lines)")
    if users:
        users = users.split()
        saved_runs_qs = saved_runs_qs.filter(uid__in=users)
        counts_df = counts_df[counts_df.index.isin(users)]
        st.dataframe(
            pd.DataFrame.from_records(
                [
                    {
                        "created_at": sr.created_at.astimezone(pytz.timezone(timezone)),
                        "workflow": sr.get_workflow_display(),
                        "run_id": sr.run_id,
                        "uid": sr.uid,
                        "url": sr.get_app_url(),
                        "run_time": str(sr.run_time),
                        "run_status": sr.run_status,
                    }
                    for sr in saved_runs_qs
                ]
            )
        )

    st.write(
        """
#### Top Recipes
        """
    )

    total_runs = (
        counts_df.sum(numeric_only=True)
        .rename("Total Runs")
        .to_frame()
        .reset_index(names=["slug"])
        .sort_values("Total Runs", ascending=False)
        .reset_index(drop=True)
    )

    col1, col2 = st.columns(2)

    with col1:
        st.write(total_runs)

    with col2:
        st.plotly_chart(
            px.pie(
                total_runs.iloc[2:],
                values="Total Runs",
                names="slug",
            ),
            use_container_width=True,
        )

    datepart_func = Func(
        "created_at",
        function="date_trunc",
        datepart=datepart,
        template="%(function)s('%(datepart)s', %(expressions)s)",
    )

    st.write(
        """
### Users Over Time
        """
    )
    users_over_time = (
        saved_runs_qs.annotate(datepart=datepart_func)
        .values("datepart")
        .annotate(unique_users=Count("uid", distinct=True))
        .values("datepart", "unique_users")
        .order_by("datepart")
    )
    st.plotly_chart(
        px.bar(
            users_over_time,
            x="datepart",
            y="unique_users",
        ),
        use_container_width=True,
    )

    st.write(
        """
### Runs Over Time
Pro Tip: double click on any recipe to drill-down
        """
    )
    runs_over_time = list(
        saved_runs_qs.annotate(datepart=datepart_func)
        .values("datepart")
        .annotate(
            total_runs=Count("run_id"),
            **{
                workflow.label: Count("run_id", filter=Q(workflow=workflow))
                for workflow in sorted_workflows
            },
        )
        .values("datepart", *[workflow.label for workflow in sorted_workflows])
        .order_by("datepart")
    )
    st.plotly_chart(
        go.Figure(
            data=[
                go.Bar(
                    name=workflow.label,
                    x=[row["datepart"] for row in runs_over_time],
                    y=[row[workflow.label] for row in runs_over_time],
                    offsetgroup=0,
                    text=workflow.label,
                )
                for workflow in sorted_workflows
            ],
            layout=go.Layout(
                barmode="stack",
                colorway=px.colors.qualitative.Light24,
                height=600,
            ),
        ),
        use_container_width=True,
    )


def merge_user_data(df: pd.DataFrame, uids: list[str]) -> pd.DataFrame:
    users_df = pd.DataFrame.from_records(
        [
            {
                "uid": u["uid"],
                "display_name": u["display_name"],
                "email": u["email"] or u["phone_number"],
                "balance": u["balance"],
            }
            for u in AppUser.objects.filter(uid__in=uids).values(
                "uid", "display_name", "email", "phone_number", "balance"
            )
        ]
    )
    df = users_df.merge(df, on="uid")
    df = df.set_index("uid")
    return df


class DateTrunc(Func):
    function = "POSITION"
    template = "%(function)s('%(substring)s' in %(expressions)s)"

    def __init__(self, expression, substring):
        # substring=substring is an SQL injection vulnerability!
        super().__init__(expression, substring=substring)


def get_filtered_app_users(
    *,
    exclude_anon: bool,
    exclude_disabled: bool,
    exclude_team: bool,
) -> QuerySet[AppUser]:
    qs = AppUser.objects.all()
    if exclude_anon:
        qs = qs.exclude(is_anonymous=True)
    if exclude_disabled:
        qs = qs.exclude(is_disabled=True)
    if exclude_team:
        qs = qs.exclude(team_user_Q)
    return qs


# def user_sign_in_time(user, timezone):
#     return firebase_timestamp_to_datetime(
#         user.user_metadata.last_sign_in_timestamp, timezone
#     )
#
#
# def firebase_timestamp_to_datetime(timestamp, timezone):
#     if not timestamp:
#         return
#     return datetime.datetime.fromtimestamp(timestamp / 1000, pytz.timezone(timezone))


if __name__ == "__main__":
    with ThreadPool(1000) as pool:
        main()
