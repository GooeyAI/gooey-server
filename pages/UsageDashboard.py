import datetime
import typing
from multiprocessing.pool import ThreadPool

import pandas as pd
import plotly.express as px
import pytz
import streamlit as st
from firebase_admin import auth
from google.cloud import firestore

from daras_ai_v2 import db
from daras_ai_v2.base import USER_RUNS_COLLECTION

st.set_page_config(layout="wide")


team_emails = [
    "devxpy@gmail.com",
    "devxpy.spam@gmail.com",
    "sean@blagsvedt.com",
    "ambika@ajaibghar.com",
    "faraazmohd07@gmail.com",
]


def user_repr(user: auth.UserRecord):
    ret = user.email or user.phone_number or user.uid
    if user.display_name:
        first_name = user.display_name.split(" ")[0]
        ret = f"{first_name} ({ret})"
    return ret


def is_team_user(user):
    return user.email and (
        user.email in team_emails
        or user.email.endswith("dara.network")
        or user.email.endswith("gooey.ai")
        or user.email.endswith("jaaga.in")
    )


def flatten(l1):
    return [it for l2 in l1 for it in l2]


def map_paginated(pool, func, sequence, batch_size=100):
    pages = [sequence[i : i + batch_size] for i in range(0, len(sequence), batch_size)]
    return flatten(pool.map(func, pages))


def flat_map(pool, func, iterable):
    return flatten(pool.map(func, iterable))


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
        time_axis = st.selectbox("Frequency", options=["1D", "1W"])
    with col3:
        timezone = st.text_input("Timezone", value="Asia/Kolkata")

    col1, col2, col3 = st.columns(3)
    with col1:
        exclude_anon = st.checkbox("Exclude Anonymous", value=True)
    with col2:
        exclude_team = st.checkbox("Exclude Team", value=True)
    with col3:
        exclude_disabled = st.checkbox("Exclude Banned", value=True)

    if st.button("Clear Cache"):
        fetch_balances.clear()
        get_auth_users.clear()
        get_all_doc_users.clear()
        fetch_page_runs.clear()

    now = datetime.datetime.now(pytz.timezone(timezone))
    today = datetime.datetime.date(now)
    time_offset = today - pd.offsets.Day(last_n_days - 1)
    print(time_offset)

    doc_users = get_all_doc_users()

    auth_users = get_filtered_auth_users(
        user_ids=[doc.id for doc in doc_users],
        exclude_anon=exclude_anon,
        exclude_disabled=exclude_disabled,
        exclude_team=exclude_team,
    )

    st.write(
        """
### Recently Signed In Users
"""
    )
    user_signups_df = pd.DataFrame.from_records(
        [
            {
                "ID": user.uid,
                "Name": user.display_name,
                "Email": user.email or user.phone_number,
                "Created": user_creation_time(user, timezone),
                "Last Sign In": user_sign_in_time(user, timezone),
            }
            for user in auth_users.values()
            if (user.user_metadata.last_sign_in_timestamp or 0)
            > (time_offset.timestamp() * 1000)
        ]
    )
    user_signups_df["Created"] = pd.to_datetime(user_signups_df["Created"])
    user_signups_df["Last Sign In"] = pd.to_datetime(user_signups_df["Last Sign In"])
    user_signups_df = user_signups_df.sort_values(
        "Last Sign In", ascending=False
    ).reset_index(drop=True)

    st.dataframe(user_signups_df)

    balances = fetch_balances(set(auth_users.keys()))

    runs = fetch_runs(user_ids=set(auth_users.keys()), time_offset=time_offset)

    runs_df = pd.DataFrame.from_records(
        [
            {
                "updated_at": data["updated_at"],
                "balance": balances[user.uid],
                "user": user_repr(user),
                "slug": doc.reference.parent.id.split("#")[0],
                "run_id": doc.id,
                "uid": user.uid,
                "url": f"https://gooey.ai/{doc.reference.parent.id}/?uid={user.uid}&run_id={doc.id}",
            }
            for doc in runs
            if (data := doc.to_dict())
            and (user := auth_users[doc.reference.parent.parent.id])
        ],
    ).convert_dtypes()

    runs_df["updated_at"] = pd.to_datetime(runs_df["updated_at"]).dt.tz_convert(
        timezone
    )
    runs_df = runs_df.sort_values("updated_at").set_index("updated_at")

    # st.write(runs_df)

    st.write(
        """
### Top Users
Pro Tip: Click on the table, then Press Ctrl/Cmd + F to search. 
Press Ctrl/Cmd + A to copy all and paste into a excel.
"""
    )
    counts_df = (
        runs_df[["uid", "user", "balance", "slug", "run_id"]]
        .groupby(["uid", "user", "balance", "slug"])
        .count()
        .reset_index()
        .pivot(
            index=["uid", "user", "balance"],
            columns="slug",
            values="run_id",
        )
        .reset_index()
    )
    counts_df["All recipes"] = (
        runs_df[["run_id", "uid"]].groupby(["uid"]).count().reset_index()[["run_id"]]
    )
    counts_df = counts_df.sort_values("All recipes", ascending=False)
    counts_df = counts_df.reset_index(drop=True)

    st.write(counts_df)

    users = st.text_area("Filter users (User ID)")
    if users:
        users = users.split()
        if st.checkbox("Want to ban users?") and st.button("💀 Ban em all"):
            with st.spinner("😁 Banning these ugly mofos..."):
                for uid in users:
                    auth.update_user(uid, disabled=True)
        counts_df = counts_df[counts_df["uid"].isin(users)]
        runs_df = runs_df[runs_df["uid"].isin(users)]
        st.write(runs_df)

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
    st.write(
        """
### Users Over Time
Pro Tip: double click on any user to drill-down
"""
    )
    df_bar = runs_df[["user"]].resample(time_axis).nunique()
    df_bar = df_bar.reset_index()
    df_bar.columns = ["updated_at", "Unique Users"]

    st.plotly_chart(
        px.bar(
            df_bar,
            x="updated_at",
            y="Unique Users",
            color_discrete_sequence=px.colors.qualitative.Light24,
        ),
        use_container_width=True,
    )

    df_area = runs_df[["user"]].groupby("user").resample(time_axis).count()
    df_area = df_area.reset_index(1)
    df_area.columns = ["updated_at", "Total Runs"]
    df_area = df_area[df_area["Total Runs"] > 0]

    st.plotly_chart(
        px.bar(
            df_area,
            x="updated_at",
            y="Total Runs",
            color=df_area.index,
            text=df_area.index,
            color_discrete_sequence=px.colors.qualitative.Light24,
        ),
        use_container_width=True,
    )

    st.write(
        """
### Recipes Over Time
Pro Tip: double click on any recipe to drill-down
"""
    )
    df_area = runs_df[["slug"]].groupby("slug").resample(time_axis).count()
    df_area = df_area.reset_index(1)
    df_area.columns = ["updated_at", "Total Runs"]
    df_area = df_area[df_area["Total Runs"] > 0]

    st.plotly_chart(
        px.bar(
            df_area,
            x="updated_at",
            y="Total Runs",
            color=df_area.index,
            text=df_area.index,
            color_discrete_sequence=px.colors.qualitative.Light24,
        ),
        use_container_width=True,
    )


@st.cache_resource
def fetch_balances(user_ids: typing.Iterable[str]):
    return dict(
        pool.map(
            lambda uid: (
                uid,
                db.get_doc_field(db.get_user_doc_ref(uid), db.USER_BALANCE_FIELD, 0),
            ),
            user_ids,
        )
    )


def get_filtered_auth_users(
    *,
    user_ids: list[str],
    exclude_anon: bool,
    exclude_disabled: bool,
    exclude_team: bool,
) -> dict[str, auth.UserRecord]:
    def _filter():
        for user in auth_users:
            if exclude_anon and not (
                user.display_name or user.email or user.phone_number
            ):
                continue
            if exclude_team and is_team_user(user):
                continue
            if exclude_disabled and user.disabled:
                continue
            yield user

    auth_users = get_auth_users(user_ids)
    auth_users = list(_filter())
    print("filtered users:", len(auth_users))
    return {user.uid: user for user in auth_users}


@st.cache_resource
def get_auth_users(user_ids: list[str]) -> list[auth.UserRecord]:
    return map_paginated(
        pool,
        lambda ids: auth.get_users([auth.UidIdentifier(i) for i in ids]).users,
        user_ids,
    )


@st.cache_resource
def get_all_doc_users() -> list[firestore.DocumentReference]:
    doc_users = list(db.get_collection_ref("user_runs").list_documents())
    print("doc users:", len(doc_users))
    return doc_users


@st.cache_resource
def fetch_runs(
    *,
    user_ids: set[str],
    time_offset,
) -> list[firestore.DocumentSnapshot]:
    page_runs = fetch_page_runs(user_ids)

    runs: list[firestore.DocumentSnapshot] = flat_map(
        pool,
        lambda page: (
            page.where("updated_at", ">", time_offset).select(["updated_at"]).get()
        ),
        page_runs,
    )
    print("runs:", len(runs))

    return runs


@st.cache_resource
def fetch_page_runs(user_ids: set[str]) -> list[firestore.CollectionReference]:
    page_runs = flat_map(
        pool,
        lambda uid: db.get_doc_ref(
            document_id=uid, collection_id=USER_RUNS_COLLECTION
        ).collections(),
        user_ids,
    )
    print("pages:", len(page_runs))
    return page_runs


def user_creation_time(user, timezone):
    return firebase_timestamp_to_datetime(
        user.user_metadata.creation_timestamp, timezone
    )


def user_sign_in_time(user, timezone):
    return firebase_timestamp_to_datetime(
        user.user_metadata.last_sign_in_timestamp, timezone
    )


def firebase_timestamp_to_datetime(timestamp, timezone):
    if not timestamp:
        return
    return datetime.datetime.fromtimestamp(timestamp / 1000, pytz.timezone(timezone))


if __name__ == "__main__":
    with ThreadPool(1000) as pool:
        main()
