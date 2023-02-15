import datetime
import math

import pandas as pd
import plotly.express as px
import pytz
import streamlit as st
from firebase_admin import auth
from google.cloud import firestore

from daras_ai_v2 import db
from daras_ai_v2.face_restoration import map_parallel

st.set_page_config(layout="wide")

st.write("## User Selection")

batch_size = 100
team_emails = [
    "devxpy@gmail.com",
    "devxpy.spam@gmail.com",
    "sean@blagsvedt.com",
    "ambika@ajaibghar.com",
    "faraazmohd07@gmail.com",
]

user_run_counts = st.session_state.setdefault("user_runs", [])
if not user_run_counts:
    with st.spinner("fetching user IDs..."):
        db_collection = firestore.Client().collection("user_runs")
        user_run_counts.extend(db_collection.list_documents(page_size=batch_size))

all_user_ids = [doc.id for doc in user_run_counts]
# st.json(all_user_ids, expanded=False)

all_users: list[auth.UserRecord] = st.session_state.setdefault("all_users", [])
if not all_users:
    with st.spinner("fetching users..."):
        for i in range(math.ceil(len(all_user_ids) / batch_size)):
            doc_ids_batch = all_user_ids[i * batch_size : (i + 1) * batch_size]
            doc_ids_batch = [auth.UidIdentifier(uid) for uid in doc_ids_batch]
            result = auth.get_users(doc_ids_batch)
            all_users.extend(result.users)

col1, col2, col3 = st.columns(3)
with col1:
    exclude_anon = st.checkbox("Exclude Anonymous", value=True)
if exclude_anon:
    all_users = [
        user
        for user in all_users
        if (user.display_name or user.email or user.phone_number)
    ]

with col2:
    exclude_team = st.checkbox("Exclude Team", value=True)
if exclude_team:
    all_users = [
        user
        for user in all_users
        if not (
            user.email
            and (user.email.endswith("dara.network") or user.email.endswith("gooey.ai"))
        )
        and not (user.email in team_emails)
    ]

with col3:
    exclude_disabled = st.checkbox("Exclude Banned", value=True)
if exclude_disabled:
    all_users = [user for user in all_users if not user.disabled]


col1, col2, col3 = st.columns(3)
with col1:
    last_n_days = st.number_input("Last n Days", min_value=1, value=14)
with col2:
    time_axis = st.selectbox("Frequency", options=["1D", "1W"])
with col3:
    timezone = st.text_input("Timezone", value="Asia/Kolkata")

now = datetime.datetime.now(pytz.timezone(timezone))
today = datetime.datetime.date(now)
time_offset = today - pd.offsets.Day(last_n_days - 1)


st.write("### Recently Signed In Users")


def user_creation_time(user):
    return firebase_timestamp_to_datetime(user.user_metadata.creation_timestamp)


def user_sign_in_time(user):
    return firebase_timestamp_to_datetime(user.user_metadata.last_sign_in_timestamp)


def firebase_timestamp_to_datetime(timestamp):
    if not timestamp:
        return
    return datetime.datetime.fromtimestamp(timestamp / 1000, pytz.timezone(timezone))


user_signups = pd.DataFrame.from_records(
    [
        {
            "ID": user.uid,
            "Name": user.display_name,
            "Email": user.email or user.phone_number,
            "Created": user_creation_time(user),
            "Last Sign In": user_sign_in_time(user),
        }
        for user in all_users
        if (user.user_metadata.last_sign_in_timestamp or 0)
        > (time_offset.timestamp() * 1000)
    ]
)
user_signups["Created"] = pd.to_datetime(user_signups["Created"])
user_signups["Last Sign In"] = pd.to_datetime(user_signups["Last Sign In"])
user_signups = user_signups.sort_values("Last Sign In", ascending=False)
user_signups.reset_index()

st.dataframe(user_signups)
# st.json(
#     [f"{user.display_name} ({user.email or user.phone_number})" for user in all_users],
#     expanded=False,
# )

user_run_counts, user_runs_by_time = st.session_state.setdefault(
    f"user_runs#{exclude_anon}#{exclude_team}#{exclude_disabled}", ([], [])
)
if not user_run_counts:
    with st.spinner(f"fetching user runs..."):

        def _fetch_total_runs(user: auth.UserRecord):
            recipes = list(
                firestore.Client()
                .collection("user_runs")
                .document(user.uid)
                .collections()
            )

            profile = db.get_user_doc_ref(user.uid).get().to_dict() or {}

            run_counts = {}

            for recipe in recipes:
                runs = recipe.select(["updated_at"]).get()
                run_counts[recipe.id] = len(runs)

                for snap in runs:
                    updated_at = snap.to_dict().get("updated_at")
                    if not updated_at:
                        continue
                    user_runs_by_time.append((snap.id, updated_at, user, recipe.id))

            return user, profile, run_counts

        user_run_counts.extend(map_parallel(_fetch_total_runs, all_users))

# user_runs.sort(key=lambda x: sum(x[1].values()), reverse=True)

"""
## Top Users
Pro Tip: Click on the table, then Press Ctrl/Cmd + F to search. 
Press Ctrl/Cmd + A to copy all and paste into a excel.
"""


def user_repr(user: auth.UserRecord):
    ret = user.email or user.phone_number or user.uid
    if user.display_name:
        first_name = user.display_name.split(" ")[0]
        ret = f"{first_name} ({ret})"
    return ret


runs_df = pd.DataFrame.from_records(
    [
        {
            "Time": updated_at,
            "ID": user.uid,
            "Name": user.display_name or "",
            "User": user_repr(user),
            "Recipe": recipe,
            "Url": f"https://gooey.ai/{recipe}/?uid={user.uid}&run_id={run_id}",
        }
        for run_id, updated_at, user, recipe in user_runs_by_time
    ],
).convert_dtypes()


runs_df["Time"] = pd.to_datetime(runs_df["Time"]).dt.tz_convert(timezone)
runs_df = runs_df.sort_values("Time")
runs_df = runs_df.set_index("Time")

runs_df = runs_df[time_offset:]

filtered_users = set(runs_df["ID"])
df = pd.DataFrame.from_records(
    [
        {
            "ID": user.uid,
            "Name": user.display_name or "",
            "User": user_repr(user),
            "Balance": profile.get("balance"),
            "All": sum(run_counts.values()),
            **run_counts,
        }
        for user, profile, run_counts in user_run_counts
        if user.uid in filtered_users
    ],
).convert_dtypes()
df = df.sort_values("All", ascending=False)
df = df.reset_index(drop=True)
st.write(df)

users = st.text_area("Filter users (User ID)")
if users:
    users = users.split()
    if st.checkbox("Want to ban users?") and st.button("💀 Ban em all"):
        with st.spinner("😁 Banning these ugly mofos..."):
            for uid in users:
                auth.update_user(uid, disabled=True)
    df = df[df["ID"].isin(users)]
    runs_df = runs_df[runs_df["ID"].isin(users)]
    st.write(runs_df)

"""
## Top Recipes
"""

total_runs = df.sum().rename("Total Runs").to_frame().reset_index(names=["Recipe"])
total_runs = total_runs.sort_values("Total Runs", ascending=False)
total_runs = total_runs.reset_index(drop=True)

col1, col2 = st.columns(2)

with col1:
    st.write(total_runs)

with col2:
    st.plotly_chart(
        px.pie(
            total_runs.iloc[2:],
            values="Total Runs",
            names="Recipe",
        ),
        use_container_width=True,
    )

"""
## Users Over Time
Pro Tip: double click on any user to drill-down
"""

df_bar = runs_df[["User"]].resample(time_axis).nunique()
df_bar = df_bar.reset_index()
df_bar.columns = ["Time", "Unique Users"]

st.plotly_chart(
    px.bar(
        df_bar,
        x="Time",
        y="Unique Users",
        color_discrete_sequence=px.colors.qualitative.Light24,
    ),
    use_container_width=True,
)

df_area = runs_df[["User"]].groupby("User").resample(time_axis).count()
df_area = df_area.reset_index(1)
df_area.columns = ["Time", "Total Runs"]
df_area = df_area[df_area["Total Runs"] > 0]

st.plotly_chart(
    px.bar(
        df_area,
        x="Time",
        y="Total Runs",
        color=df_area.index,
        text=df_area.index,
        color_discrete_sequence=px.colors.qualitative.Light24,
    ),
    use_container_width=True,
)

"""
## Recipes Over Time
Pro Tip: double click on any recipe to drill-down
"""

df_area = runs_df[["Recipe"]].groupby("Recipe").resample(time_axis).count()
df_area = df_area.reset_index(1)
df_area.columns = ["Time", "Total Runs"]
df_area = df_area[df_area["Total Runs"] > 0]

st.plotly_chart(
    px.bar(
        df_area,
        x="Time",
        y="Total Runs",
        color=df_area.index,
        text=df_area.index,
        color_discrete_sequence=px.colors.qualitative.Light24,
    ),
    use_container_width=True,
)
