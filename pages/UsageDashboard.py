import numpy as np

from gooeysite import wsgi

assert wsgi

import plotly.graph_objects as go
from django.db.models import Q, QuerySet, Count, Func

from bots.models import SavedRun, Workflow

from app_users.models import AppUser
import datetime
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
    col1, col2, col3 = st.columns(3)
    with col1:
        timezone = st.selectbox(
            "Timezone",
            pytz.common_timezones,
            index=pytz.common_timezones.index("Asia/Kolkata"),
        )
        timezone = pytz.timezone(timezone)
        now = datetime.datetime.now(timezone)
        now = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with col2:
        start_time = st.date_input(
            "Start Date", value=now - datetime.timedelta(days=30)
        )
    with col3:
        end_time = st.date_input("End Date", value=now)
    time_selector = dict(created_at__gte=start_time, created_at__lte=end_time)

    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        exclude_anon = st.checkbox("Exclude Anonymous", value=True)
    with col2:
        exclude_team = st.checkbox("Exclude Team", value=True)
    with col3:
        exclude_disabled = st.checkbox("Exclude Banned", value=True)
    with col4:
        paying_filter = st.selectbox(
            "Paying Status",
            options=["All", "Free", "Paid"],
        )

    app_users = get_filtered_app_users(
        exclude_anon=exclude_anon,
        exclude_disabled=exclude_disabled,
        exclude_team=exclude_team,
        exclude_free=paying_filter == "Paid",
        exclude_paying=paying_filter == "Free",
    )

    signups = app_users.filter(**time_selector).order_by("-created_at")
    st.write(f"### {signups.count()} Sign-ups")
    user_signups_df = pd.DataFrame.from_records(
        [
            {
                "uid": user.uid,
                "display_name": user.display_name,
                "email": str(user.email or user.phone_number),
                "created_at": user.created_at.astimezone(timezone),
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
        **time_selector,
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
                    workflow.short_slug: Count("run_id", filter=Q(workflow=workflow))
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
                        "created_at": sr.created_at.astimezone(timezone),
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
        .reset_index(names=["label"])
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
                names="label",
            ),
            use_container_width=True,
        )

    total_runs = (
        counts_df.drop(columns=["display_name", "email"])
        .astype(bool)
        .sum(numeric_only=True)
        .rename("Unique Users")
        .to_frame()
        .reset_index(names=["label"])
        .sort_values("Unique Users", ascending=False)
        .reset_index(drop=True)
    )

    col1, col2 = st.columns(2)

    with col1:
        st.write(total_runs)

    with col2:
        st.plotly_chart(
            px.pie(
                total_runs.iloc[2:],
                values="Unique Users",
                names="label",
            ),
            use_container_width=True,
        )

    datepart = st.selectbox("Frequency", options=["day", "week", "hour", "month"])
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

    st.write("### Runs Over Time")

    runs_over_time = list(
        saved_runs_qs.annotate(datepart=datepart_func)
        .values("datepart")
        .annotate(
            total_runs=Count("run_id"),
            **{
                workflow.short_slug: Count("run_id", filter=Q(workflow=workflow))
                for workflow in sorted_workflows
            },
        )
        .values("datepart", *[workflow.short_slug for workflow in sorted_workflows])
        .order_by("datepart")
    )

    sorted_workflows = st.multiselect(
        "Workflows",
        options=sorted_workflows,
        default=sorted_workflows,
        format_func=lambda w: w.short_slug,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        steps = st.number_input("Forecasting steps", min_value=0, value=3)
    if steps:
        with col2:
            degree = st.number_input("Degree of polynomial", min_value=1, value=2)
        with col3:
            exclude_last = st.checkbox("Exclude last data point", value=True)
            off = -1 if exclude_last else None

    time_ = [row["datepart"] for row in runs_over_time]
    st.plotly_chart(
        go.Figure(
            data=[
                go.Bar(
                    name=workflow.short_slug,
                    x=time_ + get_extended_x(time_, steps),
                    y=yval + get_fitted_y(yval[:off], steps, degree),
                    offsetgroup=0,
                    text=workflow.short_slug,
                    marker=dict(opacity=[1] * len(time_) + [0.5] * steps),
                )
                for workflow in sorted_workflows
                if (yval := [row[workflow.short_slug] for row in runs_over_time])
            ],
            layout=go.Layout(
                barmode="stack",
                colorway=px.colors.qualitative.Light24,
                height=600,
            ),
        ),
        use_container_width=True,
    )


def get_extended_x(x: list[datetime.datetime], steps):
    return [
        x[-1] + datetime.timedelta(seconds=(x[-1] - x[-2]).total_seconds() * (i + 1))
        for i in range(steps)
    ]


def get_fitted_y(y: list[float], steps, degree):
    coeffs = np.polyfit(range(len(y)), y, degree)
    return [np.polyval(coeffs, i) for i in range(len(y), len(y) + steps)]
    # params = scipy.optimize.curve_fit(f, range(len(y)), y)[0]
    # return [f(i, *params) for i in range(len(y), len(y) + steps)]


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


def get_filtered_app_users(
    *,
    exclude_anon: bool,
    exclude_disabled: bool,
    exclude_team: bool,
    exclude_free: bool,
    exclude_paying: bool,
) -> QuerySet[AppUser]:
    qs = AppUser.objects.all()
    if exclude_anon:
        qs = qs.exclude(is_anonymous=True)
    if exclude_disabled:
        qs = qs.exclude(is_disabled=True)
    if exclude_team:
        qs = qs.exclude(team_user_Q)
    if exclude_free:
        qs = qs.filter(is_paying=True)
    if exclude_paying:
        qs = qs.exclude(is_paying=True)
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
    main()
